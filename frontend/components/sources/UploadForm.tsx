"use client";

import { useRef, useState } from "react";
import { api, type UploadResult } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { Icon } from "../icons";
import { Button, Card, cx, ErrorBanner, inputClass, labelClass } from "../ui";

const ACCEPT = ".pdf,.md,.markdown,.html,.htm,.txt";

/** Admin-only upload. The API answers 201 (new version) or 200 (duplicate content). */
export function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.upload(file, title.trim() || undefined);
      setResult(res);
      setFile(null);
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-6 p-5">
      <form onSubmit={submit} className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] lg:items-end">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) setFile(dropped);
          }}
          className={cx(
            "flex cursor-pointer items-center gap-3.5 rounded-xl border border-dashed px-4 py-3.5 transition-colors",
            dragging
              ? "border-accent bg-accent-soft/50"
              : "border-line-strong bg-paper/50 hover:border-ink-4 hover:bg-paper",
          )}
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface text-ink-2">
            <Icon name="upload" className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            {file ? (
              <>
                <span className="block truncate text-[13.5px] font-medium text-ink">
                  {file.name}
                </span>
                <span className="block text-[12px] text-ink-3">{formatBytes(file.size)}</span>
              </>
            ) : (
              <>
                <span className="block text-[13.5px] font-medium text-ink">
                  Drop a file or <span className="underline underline-offset-2">browse</span>
                </span>
                <span className="block text-[12px] text-ink-3">PDF, Markdown, HTML or text</span>
              </>
            )}
          </span>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            data-testid="upload-file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="sr-only"
          />
        </label>
        <label className={labelClass}>
          Title <span className="font-normal text-ink-4">(optional)</span>
          <input
            className={`${inputClass} mt-1.5`}
            value={title}
            maxLength={500}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Defaults to the file name"
          />
        </label>
        <Button type="submit" variant="primary" disabled={!file || busy} className="lg:mb-px">
          {busy ? "Uploading…" : "Upload and index"}
        </Button>
      </form>
      <div className="mt-3 space-y-2 empty:hidden">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
        {result && (
          <p
            className={cx(
              "rounded-lg px-3.5 py-2.5 text-[13px]",
              result.duplicate ? "bg-warn-soft text-warn" : "bg-ok-soft text-ok",
            )}
          >
            {result.duplicate
              ? `Duplicate: "${result.title}" already has this exact content (v${result.version.version_number}). Nothing new to index.`
              : `Uploaded "${result.title}" as v${result.version.version_number}. Processing in the background…`}
          </p>
        )}
      </div>
    </Card>
  );
}
