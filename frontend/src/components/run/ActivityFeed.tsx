"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { CircleAlert, CircleCheck, Globe } from "lucide-react";
import { useEffect, useState } from "react";

import type { ActivityEvent } from "@/hooks/useResearchSocket";
import { messageForNode, WITTY_MESSAGES } from "@/lib/activityMessages";

interface ActivityFeedProps {
  status: string | null;
  currentNode: string | null;
  activity: ActivityEvent[];
}

const WITTY_ROTATE_MS = 5500;
const FEED_VISIBLE_COUNT = 7;

// Only node_finished (a completed step) and source_found (a discovery) get
// their own feed row — node_started only drives the headline above. Showing
// both a "started: X" and a "finished: X" row for the same node a moment
// apart reads as a duplicate, not two distinct events worth logging.
function isFeedWorthy(event: ActivityEvent): boolean {
  return event.kind === "node_finished" || event.kind === "source_found";
}

function FeedRow({ event }: { event: ActivityEvent }) {
  if (event.kind === "source_found" && event.source) {
    const { title, domain } = event.source;
    return (
      <>
        <Globe size={14} className="shrink-0 text-fg-subtle" />
        <span className="truncate text-fg-muted">
          Found <span className="text-fg">{title ?? domain ?? "a new source"}</span>
          {domain && title ? <span className="text-fg-subtle"> — {domain}</span> : null}
        </span>
      </>
    );
  }

  const { label, icon: Icon } = messageForNode(event.node);
  return (
    <>
      <CircleCheck size={14} className="shrink-0 text-fg-subtle" />
      <Icon size={14} className="shrink-0 text-fg-subtle" />
      <span className="text-fg-muted">{label}</span>
    </>
  );
}

export function ActivityFeed({ status, currentNode, activity }: ActivityFeedProps) {
  const reduceMotion = useReducedMotion();
  const isActive = status === "pending" || status === "running";
  const isError = status === "error";

  const [wittyIndex, setWittyIndex] = useState(() => Math.floor(Math.random() * WITTY_MESSAGES.length));
  useEffect(() => {
    if (!isActive) return;
    const id = setInterval(() => setWittyIndex((i) => (i + 1) % WITTY_MESSAGES.length), WITTY_ROTATE_MS);
    return () => clearInterval(id);
  }, [isActive]);

  const headline = isActive ? messageForNode(currentNode) : null;
  const visibleFeed = activity.filter(isFeedWorthy).slice(-FEED_VISIBLE_COUNT);

  return (
    <div className="flex w-full flex-col gap-5">
      <div className="flex min-h-[52px] flex-col justify-center gap-1.5">
        <AnimatePresence mode="wait" initial={false}>
          {isActive && headline ? (
            <motion.div
              key={headline.label}
              initial={reduceMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="flex items-center gap-2.5"
            >
              <span className="hero-breathing inline-block h-2 w-2 shrink-0 rounded-full bg-fg" />
              <headline.icon size={18} className="shrink-0 text-fg-muted" />
              <span className="font-[family-name:var(--font-display)] text-lg font-semibold text-fg">
                {headline.label}…
              </span>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2.5"
            >
              {isError ? <CircleAlert size={18} className="shrink-0 text-fg-muted" /> : null}
              <span className="font-[family-name:var(--font-display)] text-lg font-semibold text-fg">
                {isError ? "Something went wrong" : status === "completed" ? "Research complete" : "Getting started…"}
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {isActive && (
          <AnimatePresence mode="wait">
            <motion.p
              key={wittyIndex}
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduceMotion ? undefined : { opacity: 0 }}
              transition={{ duration: 0.5 }}
              className="pl-[26px] text-sm text-fg-subtle"
            >
              {WITTY_MESSAGES[wittyIndex]}
            </motion.p>
          </AnimatePresence>
        )}
      </div>

      <ul className="flex min-h-[180px] flex-col justify-end gap-2 border-t border-border pt-4">
        <AnimatePresence initial={false}>
          {visibleFeed.length === 0 ? (
            <motion.li
              key="empty"
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm text-fg-subtle"
            >
              Waiting for the first result…
            </motion.li>
          ) : (
            visibleFeed.map((event) => (
              <motion.li
                key={event.id}
                layout={!reduceMotion}
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="flex items-center gap-2 text-sm"
              >
                <FeedRow event={event} />
              </motion.li>
            ))
          )}
        </AnimatePresence>
      </ul>
    </div>
  );
}
