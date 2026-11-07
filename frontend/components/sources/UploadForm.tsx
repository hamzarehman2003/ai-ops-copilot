"use client";

import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Icon } from "../icons";

const ACCEPT = ".pdf,.md,.markdown,.html,.htm,.txt";

/** Admin-only upload. The API answers 201 (new version) or 200 (duplicate content). */
export function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const titleId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const res = await api.upload(file, title.trim() || undefined);
      if (res.duplicate) {
        toast.warning(`Duplicate: "${res.title}"`, {
          description: `This exact content is already v${res.version.version_number}. Nothing new to index.`,
        });
      } else {
        toast.success(`Uploaded "${res.title}" as v${res.version.version_number}`, {
          description: "Processing in the background…",
        });
      }
      setFile(null);
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    } catch (err) {
      toast.error(`Upload failed${file ? `: ${file.name}` : ""}`, {
        description: errorMessage(err),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-6 gap-4 rounded-lg shadow-card ring-0 border">
      <CardHeader>
        <p className="eyebrow text-muted-foreground">Upload</p>
        <CardTitle className="text-[15px] font-semibold">Add a source</CardTitle>
        <CardDescription className="text-ui">
          New versions are indexed in the background and swapped in once they are ready.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={submit}
          className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] lg:items-end"
        >
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
            className={cn(
              "flex cursor-pointer items-center gap-3.5 rounded-lg border border-dashed px-4 py-3 transition-colors has-focus-visible:border-ring has-focus-visible:ring-3 has-focus-visible:ring-ring/50",
              dragging
                ? "border-primary bg-primary/5"
                : "border-input bg-muted/30 hover:border-primary/40 hover:bg-muted/50",
            )}
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-card text-foreground/80 shadow-card">
              <Icon name="upload" className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              {file ? (
                <>
                  <span className="block truncate text-body font-medium text-foreground">
                    {file.name}
                  </span>
                  <span className="numeric block text-caption text-muted-foreground">
                    {formatBytes(file.size)}
                  </span>
                </>
              ) : (
                <>
                  <span className="block text-body font-medium text-foreground">
                    Drop a file or <span className="underline underline-offset-2">browse</span>
                  </span>
                  <span className="block text-meta text-muted-foreground">
                    PDF, Markdown, HTML or text
                  </span>
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
          <div className="grid gap-1.5">
            <Label htmlFor={titleId} className="text-ui text-foreground/80">
              Title <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id={titleId}
              className="h-9 bg-card shadow-card"
              value={title}
              maxLength={500}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Defaults to the file name"
            />
          </div>
          <Button type="submit" size="lg" disabled={!file || busy} className="px-3.5">
            {busy ? (
              <>
                <span className="size-3.5 animate-spin rounded-full border-[1.5px] border-primary-foreground/40 border-t-primary-foreground" />
                Uploading…
              </>
            ) : (
              <>
                <Icon name="upload" className="size-3.5" />
                Upload and index
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
