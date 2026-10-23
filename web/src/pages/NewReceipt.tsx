import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, putImage, type Detection, type Quad } from "../api";
import { InfoLink } from "../components/Help";
import CornerEditor from "../components/CornerEditor";
import { SubNav } from "../components/Shell";
import { canvasToJpeg, toCanvas } from "../image";

/** Long side of the original we upload; the server finds the outline on it and keeps it for reviewers. */
const ORIGINAL_MAX_SIDE = 3200; // the server crops from this, so keep enough for small text

type Phase = "pick" | "uploading" | "adjust" | "applying";

/**
 * Pick or shoot a photo → upload the original → the server finds the receipt's corners →
 * the user checks or drags them → the server crops → analysis starts.
 * `/new` creates a receipt; `/receipts/:id/photo` replaces the photo of an existing one.
 */
export default function NewReceipt() {
  const { id: existingId } = useParams();
  const [receiptId, setReceiptId] = useState<string | null>(existingId ?? null);
  const [phase, setPhase] = useState<Phase>("pick");
  const [preview, setPreview] = useState<string | null>(null);
  const [detection, setDetection] = useState<Detection | null>(null);
  const [quad, setQuad] = useState<Quad | null>(null);
  const [wholePhoto, setWholePhoto] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  async function pick(file: File | undefined) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("이미지 파일만 올릴 수 있어요.");
      return;
    }
    setError(null);
    setDetection(null);
    setQuad(null);
    setWholePhoto(false);
    setPhase("uploading");
    try {
      const blob = await canvasToJpeg(await toCanvas(file, ORIGINAL_MAX_SIDE), 0.92);
      setPreview(URL.createObjectURL(blob)); // same pixels the server sees, so corners line up
      // The first photo of a new receipt creates it; later photos replace the original.
      const { receipt, upload } = receiptId ? await api.reuploadUrl(receiptId) : await api.create();
      setReceiptId(receipt.id);
      await putImage(upload, blob);
      const found = await api.detect(receipt.id);
      setDetection(found);
      setQuad(found.corners);
      setPhase("adjust");
    } catch (e) {
      setError((e as Error).message);
      setPhase("pick");
    }
  }

  async function confirm() {
    if (!receiptId) return;
    setError(null);
    setPhase("applying");
    try {
      await api.applyCrop(receiptId, wholePhoto ? null : quad);
      await api.uploaded(receiptId);
      navigate(`/receipts/${receiptId}`, { replace: true });
    } catch (e) {
      setError((e as Error).message);
      setPhase("adjust");
    }
  }

  const busy = phase === "uploading" || phase === "applying";
  const blurry = detection?.blurry ?? false;
  const title = existingId ? "사진 다시 올리기" : "영수증 올리기";

  return (
    <>
      <SubNav
        items={[
          { label: "내 증빙", to: "/receipts" },
          ...(existingId ? [{ label: "증빙", to: `/receipts/${existingId}` }] : []),
          { label: title },
        ]}
      />
      <main className="page">
        <div className="capture">
          <div className="page-head" style={{ marginBottom: 0 }}>
            <div>
              <h1>{title}<InfoLink topic="photo" /></h1>
              <p>영수증 테두리를 확인하고 올리면 분석이 시작되고, 그동안 챗봇이 필요한 정보를 여쭤봐요.</p>
            </div>
          </div>

          <input ref={input} type="file" accept="image/*" capture="environment" hidden
            onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />

          {preview && detection ? (
            <div className="preview">
              <CornerEditor src={preview} width={detection.width} height={detection.height}
                quad={wholePhoto ? null : quad} onChange={setQuad} />
            </div>
          ) : preview ? (
            <div className="preview capture-wait">
              <img src={preview} alt="선택한 영수증" />
              <div className="overlay"><div><div className="spinner" />영수증 테두리를 찾는 중이에요</div></div>
            </div>
          ) : (
            <button className="dropzone" disabled={busy} onClick={() => input.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
                <path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
              </svg>
              <strong>영수증 촬영 또는 사진 선택</strong>
              <span className="muted small">휴대폰에서는 카메라가 바로 열려요</span>
            </button>
          )}

          {detection && (
            <div className="capture-status">
              {wholePhoto ? (
                <span className="small">사진 전체를 그대로 올려요.</span>
              ) : detection.found ? (
                <span className="small">테두리를 찾았어요. 맞지 않으면 동그라미를 끌어 영수증 모서리에 맞춰 주세요.</span>
              ) : (
                <span className="small">테두리를 찾지 못했어요. 동그라미를 끌어 영수증 네 모서리에 맞춰 주세요.</span>
              )}
              <button className="link-btn" disabled={busy} onClick={() => setWholePhoto((v) => !v)}>
                {wholePhoto ? "테두리 다시 맞추기" : "자르지 않고 올리기"}
              </button>
            </div>
          )}

          {blurry && (
            <div className="alert warn" role="alert">
              <span>사진이 흐려서 글자를 잘못 읽을 수 있어요. 다시 찍어 주세요.</span>
            </div>
          )}

          {phase === "pick" && (
            <section className="panel panel-body">
              <ul className="tips">
                <li>영수증 네 모서리가 모두 보이게 찍어 주세요.</li>
                <li>어두운 배경 위에 두면 테두리를 더 잘 찾아요.</li>
                <li>빛 반사·흔들림이 없는지 확인해 주세요.</li>
              </ul>
            </section>
          )}

          {error && <div className="alert error">{error}</div>}

          <div style={{ display: "flex", gap: 8 }}>
            {preview && (
              <button className={`btn btn-lg ${blurry ? "btn-primary" : "btn-ghost"}`} disabled={busy}
                onClick={() => input.current?.click()}>
                {blurry ? "다시 찍기" : "다시 선택"}
              </button>
            )}
            <button className={`btn btn-lg ${blurry ? "btn-ghost" : "btn-primary"}`} style={{ flex: 1 }}
              disabled={phase !== "adjust"} onClick={confirm}>
              {phase === "uploading" ? "사진 올리는 중…"
                : phase === "applying" ? "자르고 분석 시작하는 중…"
                : blurry ? "그래도 올리기" : "이대로 올리고 분석 시작"}
            </button>
          </div>
        </div>
      </main>
    </>
  );
}
