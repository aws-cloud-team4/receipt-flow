import { useEffect, useRef, useState } from "react";

/**
 * In-page camera for computers (webcams). Phones use the camera app through a file input instead,
 * which gives a sharper photo. Needs HTTPS or localhost; otherwise the browser has no camera API.
 */
export default function CameraCapture({ onShot, onCancel }: { onShot: (file: File) => void; onCancel: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let stopped = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("이 주소에서는 카메라를 쓸 수 없어요. 사진 선택을 이용해 주세요.");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({
        // ask for as much as the camera gives; small receipt text needs the pixels
        video: { facingMode: "environment", width: { ideal: 3840 }, height: { ideal: 2160 } },
        audio: false,
      })
      .then((s) => {
        if (stopped) return s.getTracks().forEach((t) => t.stop());
        stream = s;
        if (video.current) video.current.srcObject = s;
      })
      .catch((e: DOMException) => setError(cameraError(e)));
    return () => {
      stopped = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function shoot() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    canvas.toBlob(
      (b) => b ? onShot(new File([b], "camera.jpg", { type: "image/jpeg" })) : setError("사진을 만들지 못했어요. 다시 찍어 주세요."),
      "image/jpeg",
      0.95,
    );
  }

  return (
    <div className="camera">
      {error ? (
        <div className="alert error" role="alert">{error}</div>
      ) : (
        <>
          <div className="camera-view">
            <video ref={video} autoPlay playsInline muted onLoadedMetadata={() => setReady(true)} />
            {!ready && <div className="overlay"><div><div className="spinner" />카메라를 켜는 중이에요</div></div>}
          </div>
          <p className="muted small">영수증이 화면을 가득 채우게 비춰 주세요. 글씨가 흐리면 휴대폰으로 찍은 사진을 선택해 주세요.</p>
        </>
      )}
      <div className="camera-actions">
        <button className="btn btn-lg btn-ghost" onClick={onCancel}>{error ? "닫기" : "취소"}</button>
        {!error && (
          <button className="btn btn-lg btn-primary" style={{ flex: 1 }} disabled={!ready} onClick={shoot}>촬영</button>
        )}
      </div>
    </div>
  );
}

function cameraError(e: DOMException): string {
  if (e.name === "NotAllowedError" || e.name === "SecurityError")
    return "카메라 사용이 허용되지 않았어요. 주소창 옆 카메라 권한을 허용하거나 사진 선택을 이용해 주세요.";
  if (e.name === "NotFoundError" || e.name === "OverconstrainedError")
    return "연결된 카메라가 없어요. 사진 선택을 이용해 주세요.";
  if (e.name === "NotReadableError") return "다른 프로그램이 카메라를 쓰고 있어요. 그 프로그램을 닫거나 사진 선택을 이용해 주세요.";
  return "카메라를 켜지 못했어요. 사진 선택을 이용해 주세요.";
}
