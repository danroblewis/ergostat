import { useMemo } from "react";
import { marked } from "marked";
import hljs from "highlight.js/lib/common";

/* Markdown, rendered (the Guide, an item's body, a report): code blocks highlighted. Its source is the project's own
   files and ergostat's docs, the same trust as the old page's. */
marked.use({
  renderer: {
    code({ text, lang }) {
      const html = lang && hljs.getLanguage(lang) ? hljs.highlight(text, { language: lang }).value : hljs.highlightAuto(text).value;
      return `<pre><code class="hljs${lang ? ` language-${lang}` : ""}">${html}</code></pre>`;
    },
  },
});

export function Markdown({ source, className }: { source: string; className?: string }) {
  const html = useMemo(() => marked.parse(source || "", { async: false }) as string, [source]);
  return <div className={`markdown ${className ?? ""}`.trim()} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Code shown highlighted, in a language highlight.js knows (yaml, json, python, sql...). */
export function Code({ code, lang }: { code: string; lang?: string }) {
  const html = useMemo(
    () => (lang && hljs.getLanguage(lang) ? hljs.highlight(code, { language: lang }).value : hljs.highlightAuto(code).value),
    [code, lang],
  );
  return (
    <pre>
      <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  );
}
