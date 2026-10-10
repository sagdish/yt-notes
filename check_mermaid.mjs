// Parses Mermaid diagrams with the real Mermaid parser, no browser. Run by yt_transcript.py from its
// cache folder (where mermaid + jsdom are installed), never by hand.
//   stdin:  JSON list of {"id": "...", "code": "..."}
//   stdout: JSON list of {"id": "...", "error": "..."} for every diagram that does not parse
// Some diagram types touch the DOM while parsing, so a jsdom window stands in for the browser.
import { JSDOM } from "jsdom";

const { window } = new JSDOM("");
globalThis.window = window;
globalThis.document = window.document;
const { default: mermaid } = await import("mermaid");

let input = "";
for await (const chunk of process.stdin) input += chunk;

const errors = [];
for (const { id, code } of JSON.parse(input)) {
  try {
    await mermaid.parse(code);
  } catch (e) {
    errors.push({ id, error: String(e?.message ?? e).split("\n").slice(0, 4).join(" ").slice(0, 300) });
  }
}
process.stdout.write(JSON.stringify(errors));
