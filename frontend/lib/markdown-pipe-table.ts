export type PipeTable = {
  headers: string[];
  rows: string[][];
  alignments: Array<"left" | "center" | "right" | null>;
};

export type PipeTableSegment =
  | { type: "text"; lines: string[] }
  | { type: "table"; table: PipeTable };

const DELIMITER_CELL = /^:?-{3,}:?$/;

export function parseMarkdownPipeTables(lines: string[]): PipeTableSegment[] {
  const segments: PipeTableSegment[] = [];
  let textLines: string[] = [];

  const flushText = () => {
    if (!textLines.length) return;
    segments.push({ type: "text", lines: textLines });
    textLines = [];
  };

  for (let index = 0; index < lines.length;) {
    const headers = parseRow(lines[index]);
    const delimiters = index + 1 < lines.length ? parseRow(lines[index + 1]) : null;
    const validDelimiter = headers && delimiters
      && headers.length > 0
      && headers.length === delimiters.length
      && delimiters.every((cell) => DELIMITER_CELL.test(cell.replace(/\s/g, "")));

    if (!validDelimiter || !headers || !delimiters) {
      textLines.push(lines[index]);
      index += 1;
      continue;
    }

    const rows: string[][] = [];
    let cursor = index + 2;
    while (cursor < lines.length) {
      const row = parseRow(lines[cursor]);
      if (!row || row.length !== headers.length) break;
      rows.push(row);
      cursor += 1;
    }

    // A header and delimiter with no data is usually prose that merely resembles a table.
    if (!rows.length) {
      textLines.push(lines[index], lines[index + 1]);
      index += 2;
      continue;
    }

    flushText();
    segments.push({
      type: "table",
      table: {
        headers,
        rows,
        alignments: delimiters.map((cell) => alignmentFor(cell.replace(/\s/g, ""))),
      },
    });
    index = cursor;
  }

  flushText();
  return segments;
}

export function containsMarkdownPipeTable(value: string) {
  return parseMarkdownPipeTables(value.split(/\r?\n/)).some((segment) => segment.type === "table");
}

function parseRow(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|") || !trimmed.endsWith("|")) return null;

  const cells: string[] = [];
  let cell = "";
  let escaped = false;
  for (const character of trimmed.slice(1, -1)) {
    if (escaped) {
      cell += character;
      escaped = false;
    } else if (character === "\\") {
      escaped = true;
    } else if (character === "|") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }
  if (escaped) cell += "\\";
  cells.push(cell.trim());
  return cells;
}

function alignmentFor(delimiter: string): "left" | "center" | "right" | null {
  if (delimiter.startsWith(":") && delimiter.endsWith(":")) return "center";
  if (delimiter.endsWith(":")) return "right";
  if (delimiter.startsWith(":")) return "left";
  return null;
}
