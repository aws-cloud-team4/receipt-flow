"""Admin flow: accounts in a (moto) Cognito pool, and deleting receipts in any status."""

import boto3
import pytest
from conftest import EMP, REV
from receiptflow_common.org import this_year

ADMIN = {"Authorization": "Bearer dev:adm-1:admin:admin"}
YEAR = this_year()


@pytest.fixture
def pool(monkeypatch):
    from receiptflow_common import aws

    idp = boto3.client("cognito-idp", region_name="ap-northeast-2")
    pool_id = idp.create_user_pool(
        PoolName="rf-test",
        Policies={
            "PasswordPolicy": {  # same as infra/terraform/base/auth.tf
                "MinimumLength": 10,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": False,
                "RequireUppercase": False,
            }
        },
        Schema=[
            {"Name": n, "AttributeDataType": "String", "Mutable": True}
            for n in ("department", "position", "employee_no")
        ],
    )["UserPool"]["Id"]
    for g in ("employee", "reviewer", "admin"):
        idp.create_group(UserPoolId=pool_id, GroupName=g)
    monkeypatch.setenv("RF_COGNITO_POOL_ID", pool_id)
    aws.reset()
    return idp, pool_id


def test_only_admins(api, pool):
    for who in (EMP, REV):
        assert api.get("/api/admin/users", headers=who).status_code == 403
        assert api.get("/api/admin/receipts?status=draft", headers=who).status_code == 403


def _new(api, email, department="개발부", position="사원", role="employee"):
    body = {"email": email, "name": "신입", "department": department, "position": position, "role": role}
    return api.post("/api/admin/users", headers=ADMIN, json=body)


def test_create_edit_reset_disable(api, pool):
    idp, pool_id = pool
    r = _new(api, "New.Hire@example.com")
    assert r.status_code == 201, r.text
    body = r.json()
    pw = body["temporary_password"]
    assert len(pw) >= 10 and any(c.isdigit() for c in pw) and any(c.islower() for c in pw)
    user = body["user"]
    assert user["email"] == "new.hire@example.com" and user["role"] == "employee"
    assert user["department"] == "개발부" and user["status"] == "FORCE_CHANGE_PASSWORD"
    assert user["employee_no"] == f"DEV{YEAR}001"  # department code + this year + sequence
    name = user["username"]

    assert _new(api, "new.hire@example.com").status_code == 409

    listed = api.get("/api/admin/users", headers=ADMIN).json()["items"]
    assert [u["name"] for u in listed] == ["신입"]

    r = api.patch(
        f"/api/admin/users/{name}",
        headers=ADMIN,
        json={"department": "재무회계부", "position": "", "role": "reviewer"},
    )
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    assert user["department"] == "재무회계부" and user["position"] is None and user["role"] == "reviewer"
    assert user["employee_no"] == f"DEV{YEAR}001"  # never changes with the department
    groups = [
        g["GroupName"] for g in idp.admin_list_groups_for_user(UserPoolId=pool_id, Username=name)["Groups"]
    ]
    assert groups == ["reviewer"]

    r = api.post(f"/api/admin/users/{name}/temporary-password", headers=ADMIN)
    assert r.status_code == 200 and r.json()["temporary_password"] != pw

    assert api.post(f"/api/admin/users/{name}/disable", headers=ADMIN).json()["user"]["enabled"] is False
    assert api.post(f"/api/admin/users/{name}/enable", headers=ADMIN).json()["user"]["enabled"] is True
    assert (
        api.patch("/api/admin/users/nobody@example.com", headers=ADMIN, json={"name": "x"}).status_code == 404
    )


def test_employee_numbers_follow_department_and_this_year(api, pool):
    idp, pool_id = pool
    # an account made elsewhere (seed script) already holds DEV<this year>007
    idp.admin_create_user(
        UserPoolId=pool_id,
        Username="old@example.com",
        MessageAction="SUPPRESS",
        UserAttributes=[
            {"Name": "email", "Value": "old@example.com"},
            {"Name": "custom:employee_no", "Value": f"DEV{YEAR}007"},
        ],
    )
    nos = [_new(api, f"d{i}@example.com").json()["user"]["employee_no"] for i in range(2)]
    assert nos == [f"DEV{YEAR}008", f"DEV{YEAR}009"]
    assert _new(api, "s@example.com", department="영업부").json()["user"]["employee_no"] == f"SAL{YEAR}001"
    # a duplicate email does not use up a number
    assert _new(api, "d0@example.com").status_code == 409
    assert _new(api, "d3@example.com").json()["user"]["employee_no"] == f"DEV{YEAR}010"


def test_department_and_position_come_from_the_lists(api, pool):
    idp, pool_id = pool
    assert _new(api, "x@example.com", department="없는팀").json()["error"]["code"] == "invalid_department"
    assert _new(api, "x@example.com", position="회장님").json()["error"]["code"] == "invalid_position"
    opts = api.get("/api/admin/options", headers=ADMIN).json()
    assert [d["name"] for d in opts["departments"]] == [
        "경영지원부",
        "재무회계부",
        "기획부",
        "영업부",
        "마케팅부",
        "개발부",
        "감사부",
    ]
    assert {"code": "ACC", "name": "재무회계부", "description": "회계, 결산, 증빙 검토"} in opts[
        "departments"
    ]
    assert opts["positions"][-1] == "부장" and "팀장" not in opts["positions"] and "hire_years" not in opts
    # an older account keeps a value that is no longer in the list when other fields change
    idp.admin_create_user(
        UserPoolId=pool_id,
        Username="legacy@example.com",
        MessageAction="SUPPRESS",
        UserAttributes=[
            {"Name": "email", "Value": "legacy@example.com"},
            {"Name": "custom:department", "Value": "옛날팀"},
        ],
    )
    r = api.patch(
        "/api/admin/users/legacy@example.com", headers=ADMIN, json={"name": "새이름", "department": "옛날팀"}
    )
    assert r.status_code == 200 and r.json()["user"]["department"] == "옛날팀"
    r = api.patch("/api/admin/users/legacy@example.com", headers=ADMIN, json={"department": "다른옛날팀"})
    assert r.status_code == 400


def test_admin_cannot_demote_or_disable_self(api, pool):
    idp, pool_id = pool
    idp.admin_create_user(
        UserPoolId=pool_id,
        Username="admin@dev.local",
        MessageAction="SUPPRESS",
        UserAttributes=[{"Name": "email", "Value": "admin@dev.local"}, {"Name": "name", "Value": "오태민"}],
    )
    idp.admin_add_user_to_group(UserPoolId=pool_id, Username="admin@dev.local", GroupName="admin")
    r = api.patch("/api/admin/users/admin@dev.local", headers=ADMIN, json={"role": "employee"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_demote"
    r = api.post("/api/admin/users/admin@dev.local/disable", headers=ADMIN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_disable"


def test_delete_any_status_leaves_a_record(api, pool):
    rid = api.post("/api/receipts", headers=EMP).json()["receipt"]["id"]
    s3 = boto3.client("s3", region_name="ap-northeast-2")
    s3.put_object(Bucket="rf-test-bucket", Key=f"raw/{rid}.jpg", Body=b"x")
    api.patch(
        f"/api/receipts/{rid}",
        headers=EMP,
        json={"fields": {"merchant_name": "테스트상점", "total_amount": 1000}},
    )
    from receiptflow_common import store

    store.update_receipt(rid, review_status="approved")  # past the point where employees may delete
    assert api.delete(f"/api/receipts/{rid}", headers=EMP).status_code in (403, 409)

    listed = api.get("/api/admin/receipts?status=approved", headers=ADMIN).json()["items"]
    assert [r["id"] for r in listed] == [rid]

    assert api.delete(f"/api/admin/receipts/{rid}", headers=ADMIN).status_code == 204
    assert api.get(f"/api/receipts/{rid}", headers=EMP).status_code == 404
    assert s3.list_objects_v2(Bucket="rf-test-bucket").get("KeyCount", 0) == 0
    log = api.get("/api/admin/deletions", headers=ADMIN).json()["items"]
    assert log[0]["receipt_id"] == rid and log[0]["deleted_by"] == "오태민"
    assert log[0]["merchant_name"] == "테스트상점" and log[0]["review_status"] == "approved"
    assert api.delete(f"/api/admin/receipts/{rid}", headers=ADMIN).status_code == 404


def test_delete_account_keeps_receipts(api, pool):
    idp, pool_id = pool
    name = _new(api, "leaver@example.com").json()["user"]["username"]
    assert api.delete(f"/api/admin/users/{name}", headers=ADMIN).status_code == 204
    assert [u["email"] for u in api.get("/api/admin/users", headers=ADMIN).json()["items"]] == []
    assert api.delete(f"/api/admin/users/{name}", headers=ADMIN).status_code == 404
    idp.admin_create_user(
        UserPoolId=pool_id,
        Username="admin@dev.local",
        MessageAction="SUPPRESS",
        UserAttributes=[{"Name": "email", "Value": "admin@dev.local"}],
    )
    r = api.delete("/api/admin/users/admin@dev.local", headers=ADMIN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_delete"


def test_deletion_records_can_be_removed(api, pool):
    ids = [api.post("/api/receipts", headers=EMP).json()["receipt"]["id"] for _ in range(3)]
    for rid in ids:
        assert api.delete(f"/api/admin/receipts/{rid}", headers=ADMIN).status_code == 204
    log = api.get("/api/admin/deletions", headers=ADMIN).json()["items"]
    assert len(log) == 3 and all(e["key"] for e in log)
    from urllib.parse import quote

    assert (
        api.delete(f"/api/admin/deletions/{quote(log[0]['key'], safe='')}", headers=ADMIN).status_code == 204
    )
    assert len(api.get("/api/admin/deletions", headers=ADMIN).json()["items"]) == 2
    assert (
        api.delete(f"/api/admin/deletions/{quote(log[0]['key'], safe='')}", headers=ADMIN).status_code == 404
    )
    assert api.delete("/api/admin/deletions", headers=ADMIN).status_code == 204
    assert api.get("/api/admin/deletions", headers=ADMIN).json()["items"] == []
    assert api.delete("/api/admin/deletions", headers=EMP).status_code == 403


def test_reviewers_belong_to_accounting(api, pool):
    r = _new(api, "rev@example.com", department="영업부", role="reviewer")
    assert r.status_code == 400 and r.json()["error"]["code"] == "reviewer_department"
    user = _new(api, "acc@example.com", department="재무회계부", position="대리", role="reviewer").json()[
        "user"
    ]
    assert user["role"] == "reviewer" and user["employee_no"].startswith("ACC")
    name = user["username"]
    # moving a reviewer out of accounting, or making someone elsewhere a reviewer, is refused
    r = api.patch(f"/api/admin/users/{name}", headers=ADMIN, json={"department": "개발부"})
    assert r.json()["error"]["code"] == "reviewer_department"
    emp = _new(api, "emp@example.com", department="개발부").json()["user"]["username"]
    r = api.patch(f"/api/admin/users/{emp}", headers=ADMIN, json={"role": "reviewer"})
    assert r.json()["error"]["code"] == "reviewer_department"
    r = api.patch(
        f"/api/admin/users/{emp}", headers=ADMIN, json={"role": "reviewer", "department": "재무회계부"}
    )
    assert r.status_code == 200 and r.json()["user"]["role"] == "reviewer"
    # back to employee: any department again
    r = api.patch(
        f"/api/admin/users/{name}", headers=ADMIN, json={"role": "employee", "department": "개발부"}
    )
    assert r.status_code == 200


def test_admins_have_no_department(api, pool):
    user = _new(api, "boss@example.com", department=None, position="부장", role="admin").json()["user"]
    assert user["role"] == "admin" and user["department"] is None
    assert user["employee_no"] == f"ADM{YEAR}001"
    # a department sent for an admin is ignored
    user = _new(api, "boss2@example.com", department="영업부", role="admin").json()["user"]
    assert user["department"] is None and user["employee_no"] == f"ADM{YEAR}002"
    # everyone else still needs one
    assert _new(api, "nodept@example.com", department=None).json()["error"]["code"] == "invalid_department"
