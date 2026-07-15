// Safe Markdown rendering for copilot answer_markdown (Phase 3).
//
// Security posture:
// - No raw HTML: rehype-raw is NOT installed/used, so embedded HTML tags in
//   the source render as literal escaped text, never as DOM/executed markup.
// - Unsafe URL protocols (javascript:, data:, file:, vbscript:, and anything
//   else) are rejected by react-markdown's default sanitizer AND, defense in
//   depth, by SafeAnchor below, which additionally refuses to render a
//   clickable link for anything that isn't a fully-qualified http(s)/mailto
//   URL — a relative path (e.g. "/opportunity/OPP-013") written by the model
//   is never treated as a trusted internal route; only the structured
//   `citations` array (rendered by <Citations>) can open an internal detail
//   view. External links always get target="_blank" rel="noopener noreferrer".
// - Malformed Markdown cannot crash the UI: remark/react-markdown parse
//   permissively and always produce *some* tree; nothing here throws on bad
//   input (see Markdown.test.tsx).
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ComponentPropsWithoutRef } from "react";

function isSafeAbsoluteUrl(href: unknown): href is string {
  return typeof href === "string" && /^(https?:|mailto:)/i.test(href);
}

function SafeAnchor({ href, children, ...rest }: ComponentPropsWithoutRef<"a">) {
  if (!isSafeAbsoluteUrl(href)) {
    // Not a trusted, fully-qualified external link — render as plain text
    // rather than a navigable element (never a trusted internal route).
    return <span className="md-inert-link">{children}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
      {children}
    </a>
  );
}

export default function Markdown({ text }: { text: string }) {
  return (
    <div className="md-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{ a: SafeAnchor }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
