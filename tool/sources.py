"""
sources.py — Sinh file nguon cong khai (format Google Doc nhu AI Frontier).

Doc clip-manifest.json + references.json, ghi ra build/sources.md voi:
  - Clip: mot dong = nguon + [in,out] + speaker/role
  - References: tung link kem mo ta (neu co)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manifest import load_manifest, load_references  # noqa: E402


def _fmt_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def generate(root, cfg_name=None):
    clips = load_manifest(root)
    refs = load_references(root)
    name = cfg_name or os.path.basename(root)

    lines = []
    lines.append(f"# Sources — {name}")
    lines.append("")
    lines.append("## Clips in the video")
    lines.append("")
    if clips:
        for c in clips:
            who = c["speaker"] or ""
            role = (" — " + c["role"]) if c.get("role") else ""
            note = f"  ({c['note']})" if c.get("note") else ""
            lines.append(f"- [{_fmt_time(c['in'])} - {_fmt_time(c['out'])}] "
                         f"{c['url']}  {who}{role}{note}".rstrip())
    else:
        lines.append("(khong co clip-manifest.json hoac rong)")
    lines.append("")
    lines.append("## References")
    lines.append("")
    if refs:
        for ref in refs:
            if isinstance(ref, str):
                lines.append(f"- {ref}")
            else:
                desc = ref.get("note") or ref.get("desc") or ""
                lines.append(f"- {desc}  {ref.get('url', '')}".strip())
    else:
        lines.append("(khong co references.json hoac rong)")

    out = os.path.join(root, "build", "sources.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"OK  {out}  ({len(clips)} clips, {len(refs)} refs)")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "videos/test-60s"
    generate(root)
