"use client";

import { Children, Fragment, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Modal } from "@/components/ui/Modal";
import type { Citation, EvidenceResponse, FigureResponse } from "@/types/api";
import { CitationMarker } from "./CitationMarker";
import { CitationViewer } from "./CitationViewer";
import { ReportFigure } from "./ReportFigure";

interface ReportViewProps {
  markdown: string;
  citations: Citation[];
  evidenceById: Map<string, EvidenceResponse>;
  figuresById: Map<string, FigureResponse>;
}

// A `figure://{id}` that isn't in figuresById is either a genuine backend
// hiccup (figure row deleted, etc.) or an older report generated before
// figures existed — either way, plain text beats a broken image.
function FigurePlaceholder({ alt }: { alt?: string }) {
  return (
    <span className="my-3 flex h-28 w-full items-center justify-center rounded-input border border-dashed border-border text-xs text-fg-subtle">
      Figure not available in this preview{alt ? ` — ${alt}` : ""}
    </span>
  );
}

const PROSE_CLASSES =
  "flex flex-col text-[15px] leading-relaxed text-fg " +
  "[&_h1]:mb-3 [&_h1]:mt-8 [&_h1]:text-2xl [&_h1]:font-semibold [&_h1]:tracking-[-0.01em] [&_h1]:text-fg [&_h1:first-child]:mt-0 " +
  "[&_h2]:mb-2 [&_h2]:mt-7 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-fg " +
  "[&_h3]:mb-2 [&_h3]:mt-5 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-fg " +
  "[&_p]:mb-3 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-1 " +
  "[&_a]:text-fg [&_a]:underline [&_a]:underline-offset-2 [&_strong]:font-semibold [&_strong]:text-fg " +
  "[&_table]:mb-4 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm " +
  "[&_th]:border-b [&_th]:border-border [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-fg-muted " +
  "[&_td]:border-b [&_td]:border-border [&_td]:px-3 [&_td]:py-2 " +
  "[&_blockquote]:border-l-2 [&_blockquote]:border-border-strong [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-fg-muted " +
  "[&_hr]:my-6 [&_hr]:border-border";

export function ReportView({ markdown, citations, evidenceById, figuresById }: ReportViewProps) {
  const [openMarker, setOpenMarker] = useState<number | null>(null);

  const citationByMarker = useMemo(() => {
    const map = new Map<number, Citation>();
    for (const c of citations) map.set(c.marker, c);
    return map;
  }, [citations]);

  // A paired source_image never gets its own figure:// marker (synthesizer.py
  // excludes it from the model's prompt entirely) — this is the only way it
  // ever reaches the page: found here by its paired_figure_id and rendered
  // alongside whichever illustration figure lands wherever the model placed
  // *that* marker.
  const pairedByIllustrationId = useMemo(() => {
    const map = new Map<string, FigureResponse>();
    for (const fig of figuresById.values()) {
      if (fig.paired_figure_id) map.set(fig.paired_figure_id, fig);
    }
    return map;
  }, [figuresById]);

  function withCitations(children: ReactNode): ReactNode {
    return Children.map(children, (child) => {
      if (typeof child !== "string") return child;
      const parts = child.split(/(\[\d+\])/g);
      if (parts.length === 1) return child;
      return parts.map((part, i) => {
        const match = /^\[(\d+)\]$/.exec(part);
        if (!match) return <Fragment key={i}>{part}</Fragment>;
        const marker = Number(match[1]);
        return <CitationMarker key={i} marker={marker} onClick={() => setOpenMarker(marker)} />;
      });
    });
  }

  // synthesizer.py wraps its one key-takeaway sentence per section in
  // ==...==, with the citation marker included inside the delimiters — so
  // this splits on the highlight first, then runs citation-parsing on
  // whatever text lands inside (and outside) it.
  function withHighlights(children: ReactNode): ReactNode {
    return Children.map(children, (child) => {
      if (typeof child !== "string") return child;
      const parts = child.split(/(==[^=\n]+==)/g);
      if (parts.length === 1) return withCitations(child);
      return parts.map((part, i) => {
        const match = /^==([^=\n]+)==$/.exec(part);
        if (!match) return <Fragment key={i}>{withCitations(part)}</Fragment>;
        return (
          <mark key={i} className="rounded-sm bg-accent/20 px-0.5 text-fg">
            {withCitations(match[1])}
          </mark>
        );
      });
    });
  }

  const activeCitation = openMarker != null ? citationByMarker.get(openMarker) ?? null : null;
  const activeEvidence = activeCitation ? evidenceById.get(activeCitation.evidence_id) ?? null : null;

  return (
    <>
      <article className={PROSE_CLASSES}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          // react-markdown's default urlTransform blanks any scheme outside
          // http(s)/irc(s)/mailto/xmpp, which silently empties our
          // `figure://{id}` src before the custom `img` renderer ever sees it.
          urlTransform={(url) => (url.startsWith("figure://") ? url : defaultUrlTransform(url))}
          components={{
            p: ({ node, children }) => {
              // A paragraph whose only content is a `figure://` image gets
              // swapped for ReportFigure below, which renders block-level
              // markup (a div wrapping <figure>/<figcaption>, two of them
              // side by side for a paired photo) — invalid nested inside the
              // <p> react-markdown wraps every image in by default, and a
              // real hydration error, not just a lint nitpick. Render it
              // unwrapped in that one case; every other paragraph is
              // untouched.
              const onlyChild = node?.children?.length === 1 ? node.children[0] : null;
              const isFigureOnly =
                onlyChild?.type === "element" &&
                onlyChild.tagName === "img" &&
                typeof onlyChild.properties?.src === "string" &&
                onlyChild.properties.src.startsWith("figure://");
              if (isFigureOnly) return <>{children}</>;
              return <p>{withHighlights(children)}</p>;
            },
            li: ({ children }) => <li>{withCitations(children)}</li>,
            td: ({ children }) => <td>{withCitations(children)}</td>,
            h1: ({ children }) => <h1>{withCitations(children)}</h1>,
            h2: ({ children }) => <h2>{withCitations(children)}</h2>,
            h3: ({ children }) => <h3>{withCitations(children)}</h3>,
            img: ({ src, alt }) => {
              if (typeof src === "string" && src.startsWith("figure://")) {
                const figureId = src.slice("figure://".length);
                const figure = figuresById.get(figureId);
                if (!figure) return <FigurePlaceholder alt={alt} />;
                const paired = pairedByIllustrationId.get(figure.id);
                return (
                  <ReportFigure
                    figureId={figure.id}
                    caption={figure.caption}
                    kind={figure.kind}
                    pairedPhoto={paired ? { figureId: paired.id, caption: paired.caption } : null}
                  />
                );
              }
              // eslint-disable-next-line @next/next/no-img-element -- external report images aren't known to next/image
              return <img src={src} alt={alt ?? ""} className="my-3 max-w-full rounded-input" />;
            },
          }}
        >
          {markdown}
        </ReactMarkdown>
      </article>

      <Modal
        open={openMarker != null}
        onClose={() => setOpenMarker(null)}
        title={openMarker != null ? `Citation [${openMarker}]` : undefined}
      >
        {openMarker != null && <CitationViewer marker={openMarker} evidence={activeEvidence} />}
      </Modal>
    </>
  );
}
