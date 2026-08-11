"use client";

import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface ReportFigureProps {
  figureId: string;
  caption: string;
  kind: string;
  // The real photo web_image_fetcher paired with this illustration, if any
  // (see synthesizer.py: a paired figure never gets its own figure:// marker,
  // so this is the only way it ever reaches the page). Only ever set when
  // kind === "illustration".
  pairedPhoto?: { figureId: string; caption: string } | null;
}

// A plain <img src="/api/.../file"> can't carry the Bearer token the route
// requires, so the bytes are fetched authenticated and swapped in as a blob
// URL — same pattern as ExportPdfButton's download.
function useFigureObjectUrl(figureId: string): { objectUrl: string | null; failed: boolean } {
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

  return { objectUrl, failed };
}

function FigureImage({
  figureId,
  alt,
  caption,
  widthClass,
}: {
  figureId: string;
  alt: string;
  caption: string;
  widthClass: string;
}) {
  const { objectUrl, failed } = useFigureObjectUrl(figureId);

  if (failed) {
    return (
      <span
        className={`flex h-28 items-center justify-center rounded-input border border-dashed border-border text-xs text-fg-subtle ${widthClass}`}
      >
        {caption} — could not be loaded
      </span>
    );
  }

  return (
    <figure className="flex flex-col items-center gap-2">
      {objectUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not something next/image can optimize
        <img src={objectUrl} alt={alt} className={`max-w-full rounded-input border border-border ${widthClass}`} />
      ) : (
        <span
          className={`flex h-40 items-center justify-center rounded-input border border-border bg-surface text-xs text-fg-subtle ${widthClass}`}
        >
          Loading figure…
        </span>
      )}
      <figcaption className={`text-center text-xs text-fg-muted ${widthClass}`}>{caption}</figcaption>
    </figure>
  );
}

export function ReportFigure({ figureId, caption, kind, pairedPhoto }: ReportFigureProps) {
  // An illustration has no equivalent to a chart's value-grounding check —
  // it's never derived from evidence, so every render of one must say so,
  // not just a comment at the node that generated it.
  const isIllustration = kind === "illustration";
  const displayCaption = isIllustration ? `${caption} — AI-generated illustration, not derived from evidence` : caption;

  // Charts/diagrams carry data and need the room to stay legible — full
  // column width. An illustration is decorative only; sized like a small
  // figure in a printed book, not a hero image, so it doesn't compete with
  // the report's actual content for attention. The paired real photo (when
  // present) renders a little larger than the illustration — it's the more
  // credible of the two, so it shouldn't read as the lesser image.
  const widthClass = isIllustration ? "w-56" : "w-full";
  const photoWidthClass = "w-64";

  if (isIllustration && pairedPhoto) {
    return (
      <div className="my-4 flex flex-wrap items-start justify-center gap-5">
        <FigureImage figureId={pairedPhoto.figureId} alt={pairedPhoto.caption} caption={pairedPhoto.caption} widthClass={photoWidthClass} />
        <FigureImage figureId={figureId} alt={caption} caption={displayCaption} widthClass={widthClass} />
      </div>
    );
  }

  return (
    <div className="my-4 flex justify-center">
      <FigureImage figureId={figureId} alt={caption} caption={displayCaption} widthClass={widthClass} />
    </div>
  );
}
