import { useRef, useState } from "react";
import { errorMessage, type ProofDocumentKind, uploadProof } from "../lib/api";
import type { StoredDocument } from "../types";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.zip,.txt";
const MAX_BYTES = 10 * 1024 * 1024;

const LABEL: Record<ProofDocumentKind, string> = {
  deliverable: "Upload delivered work",
  payer_confirmation: "Upload the client's confirmation",
};

export function UploadDeliverable({
  agreementId,
  onUploaded,
  kind = "deliverable",
}: {
  agreementId: string;
  onUploaded: (document: StoredDocument) => void;
  kind?: ProofDocumentKind;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const send = async (file: File | undefined) => {
    if (!file) return;
    setFailed(null);
    if (file.size > MAX_BYTES) {
      setFailed("Files can be up to 10 MB.");
      return;
    }
    setBusy(true);
    try {
      onUploaded(await uploadProof(agreementId, file, kind));
    } catch (failure) {
      setFailed(errorMessage(failure, "The file couldn't be uploaded. Try again."));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        hidden
        aria-label={kind === "deliverable" ? "Delivered work file" : "Confirmation file"}
        onChange={(event) => send(event.target.files?.[0])}
      />
      <button type="button" className="button" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Uploading…" : LABEL[kind]}
      </button>
      <span className="muted" style={{ fontSize: "0.833rem" }}>
        PDF, image, ZIP or text, up to 10 MB. Stored encrypted.
      </span>
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
    </div>
  );
}
