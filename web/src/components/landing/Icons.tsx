// Small line icons for the architecture diagram. Generic shapes drawn here (not AWS service icons).
import type { ReactNode } from "react";

export type IconName =
  | "phone" | "monitor" | "lock" | "globe" | "split" | "window" | "api" | "chat" | "crop" | "worker"
  | "bucket" | "queue" | "spark" | "db" | "git" | "play" | "stack" | "cluster";

const PATHS: Record<IconName, ReactNode> = {
  phone: <><rect x="7" y="2.5" width="10" height="19" rx="2.2" /><path d="M10.5 18.5h3" /></>,
  monitor: <><rect x="3" y="4" width="18" height="12" rx="1.6" /><path d="M9 20h6M12 16v4" /></>,
  lock: <><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5M12 14.5v2.5" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.6 2.6 2.6 15.4 0 18M12 3c-2.6 2.6-2.6 15.4 0 18" /></>,
  split: <><path d="M3 12h6M9 12l4-5h8M9 12l4 5h8M9 12h12" /><path d="M18.5 4.5 21 7l-2.5 2.5M18.5 14.5 21 17l-2.5 2.5" /></>,
  window: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 8.5h18M6 6.3h.01M8.5 6.3h.01" /></>,
  api: <><path d="M8 7 3 12l5 5M16 7l5 5-5 5M13.5 5l-3 14" /></>,
  chat: <><path d="M4 5h16v10H9l-4 4v-4H4z" /><path d="M8 9h8M8 12h5" /></>,
  crop: <><path d="M6 2.5V18h15.5M2.5 6H18v15.5" /></>,
  worker: <><circle cx="12" cy="12" r="3" /><path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1M18.7 18.7l-2.1-2.1M7.4 7.4 5.3 5.3" /></>,
  bucket: <><path d="M4 6h16l-2 14H6z" /><ellipse cx="12" cy="6" rx="8" ry="2.4" /></>,
  queue: <><rect x="2.5" y="8" width="5" height="8" rx="1" /><rect x="9.5" y="8" width="5" height="8" rx="1" /><rect x="16.5" y="8" width="5" height="8" rx="1" /></>,
  spark: <><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="M19 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></>,
  db: <><ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" /><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8" /></>,
  git: <><circle cx="6" cy="5.5" r="2.3" /><circle cx="6" cy="18.5" r="2.3" /><circle cx="18" cy="9" r="2.3" /><path d="M6 7.8v8.4M18 11.3c0 3.5-6 3-10.5 5.6" /></>,
  play: <><circle cx="12" cy="12" r="9" /><path d="M10 8.5v7l6-3.5z" /></>,
  stack: <><path d="M12 3 3 7.5l9 4.5 9-4.5z" /><path d="m3 12 9 4.5 9-4.5M3 16.5 12 21l9-4.5" /></>,
  cluster: <><path d="M12 2.5 20.5 7.5v9L12 21.5 3.5 16.5v-9z" /><path d="M12 7.5 16 9.8v4.4L12 16.5 8 14.2V9.8z" /></>,
};

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="arch-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[name]}
    </svg>
  );
}
