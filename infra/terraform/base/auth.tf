# Cognito: email sign-in, employee/reviewer groups. Users are created with scripts/seed-users.

resource "aws_cognito_user_pool" "main" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "INACTIVE"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = false
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 64
    }
  }

  # Profile shown in the app and copied onto each receipt (custom:department etc. in the ID token).
  dynamic "schema" {
    for_each = ["department", "position", "employee_no"]
    content {
      name                = schema.value
      attribute_data_type = "String"
      mutable             = true
      required            = false
      string_attribute_constraints {
        min_length = 0
        max_length = 64
      }
    }
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name                          = "${local.name}-web"
  user_pool_id                  = aws_cognito_user_pool.main.id
  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  # Users can read their profile but only admins (seed script / HR) can change it.
  read_attributes        = ["email", "email_verified", "name", "custom:department", "custom:position", "custom:employee_no"]
  write_attributes       = ["name"]
  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 7
  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_group" "role" {
  for_each     = { employee = "증빙 제출 직원", reviewer = "증빙 검수 담당자", admin = "계정·증빙 관리자" }
  name         = each.key
  user_pool_id = aws_cognito_user_pool.main.id
  description  = each.value
}
