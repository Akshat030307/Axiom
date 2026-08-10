"use client";

import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface ReportFigureProps {
  figureId: string;
  caption: string;
  kind: string;
}

// A plain <img src="/api/.../file"> can't carry the Bearer token the route
// requires, so the bytes are fetched authenticated and swapped in as a blob
// URL — same pattern as ExportPdfButton's download.
export function ReportFigure({ figureId, caption, kind }: ReportFigureProps) {
  // An illustration has no equivalent to a chart's value-grounding check —
  // it's never derived from evidence, so every render of one must say so,
  // not just a comment at the node that generated it.
  const displayCaption =
    kind === "illustration" ? `${caption} — AI-generated illustration, not derived from evidence` : caption;

  const { accessToken } = useAuth();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    let url: string | null = null;

    api
      .fetchFigureObjectUrl(accessToken, figureId)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        url = u;
        setObjectUrl(u);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [accessToken, figureId]);

  if (failed) {
    return (
      <span className="my-3 flex h-28 w-full items-center justify-center rounded-input border border-dashed border-border text-xs text-fg-subtle">
        {displayCaption} — could not be loaded
      </span>
    );
  }

  return (
    <figure className="my-4 flex flex-col items-center gap-2">
      {objectUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not something next/image can optimize
        <img src={objectUrl} alt={caption} className="max-w-full rounded-input border border-border" />
      ) : (
        <span className="flex h-40 w-full items-center justify-center rounded-input border border-border bg-surface text-xs text-fg-subtle">
          Loading figure…
        </span>
      )}
      <figcaption className="text-center text-xs text-fg-muted">{displayCaption}</figcaption>
    </figure>
  );
}
