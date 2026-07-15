import { parseMarkdownPipeTables } from "@/lib/markdown-pipe-table";

export function ReportPipeContent({
  value,
  renderText,
}: {
  value: string;
  renderText?: (lines: string[], index: number) => React.ReactNode;
}) {
  const segments = parseMarkdownPipeTables(value.split(/\r?\n/));
  return (
    <>
      {segments.map((segment, index) => segment.type === "table" ? (
        <div className="report-pipe-table-scroll" key={`table-${index}`} tabIndex={0} role="region" aria-label="报告数据表格">
          <table className="report-pipe-table">
            <thead>
              <tr>{segment.table.headers.map((header, cellIndex) => <th key={`${header}-${cellIndex}`} style={{ textAlign: segment.table.alignments[cellIndex] || undefined }}>{renderCellContent(header)}</th>)}</tr>
            </thead>
            <tbody>
              {segment.table.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex} style={{ textAlign: segment.table.alignments[cellIndex] || undefined }}>{renderCellContent(cell)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : renderText ? renderText(segment.lines, index) : (
        <div className="report-pipe-text" key={`text-${index}`}>{segment.lines.map((line, lineIndex) => <p key={lineIndex}>{line}</p>)}</div>
      ))}
    </>
  );
}

function renderCellContent(value: string) {
  const parts: React.ReactNode[] = [];
  const linkPattern = /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = linkPattern.exec(value)) !== null) {
    if (match.index > cursor) parts.push(value.slice(cursor, match.index));
    parts.push(<a href={match[2]} target="_blank" rel="noopener noreferrer" key={`${match.index}-${match[2]}`}>{match[1]}</a>);
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) parts.push(value.slice(cursor));
  return parts.length ? parts : value;
}
