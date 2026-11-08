// The production chart, drawn as SVG from the series the detector produced.
//
// No charting library, for the same reason the BM25 index is implemented rather than imported: the
// reason a point sits where it does should be readable, and a library's internals are not.
//
// **The only arithmetic here is scaling a value to a pixel**, which is presentation. The actual
// rate, the expected rate and the band are plotted as given. Protocol section 21.1 keeps any other
// derivation out of the console, and a chart that smoothed, resampled or interpolated would be
// showing a series the verdict was never judged against.
//
// A day that is not valid producing has no expectation, so the band and the expected line break
// there rather than bridging the gap. That is deliberate: the model predicts per valid producing
// day, and a continuous line across a shut-in would draw a judgement nobody made.

import type { ChartSeries, SeriesRow } from "./types";

const WIDTH = 940;
const HEIGHT = 260;
const PAD = { top: 14, right: 16, bottom: 26, left: 54 };

interface Segment {
  rows: SeriesRow[];
  from: number;
}

function segments(rows: SeriesRow[]): Segment[] {
  const out: Segment[] = [];
  let current: SeriesRow[] = [];
  let from = 0;
  rows.forEach((row, index) => {
    if (row.expected === null) {
      if (current.length > 0) out.push({ rows: current, from });
      current = [];
      return;
    }
    if (current.length === 0) from = index;
    current.push(row);
  });
  if (current.length > 0) out.push({ rows: current, from });
  return out;
}

export function Chart({ chart }: { chart: ChartSeries }): JSX.Element {
  const rows = chart.rows;
  if (rows.length === 0) return <p className="empty">No series for this episode.</p>;

  const values: number[] = [];
  rows.forEach((row) => {
    [row.actual, row.expected, row.lower, row.upper].forEach((value) => {
      if (value !== null) values.push(value);
    });
  });
  const top = Math.max(...values) * 1.06;
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (index: number) => PAD.left + (index / Math.max(rows.length - 1, 1)) * plotWidth;
  const y = (value: number) => PAD.top + plotHeight - (value / top) * plotHeight;

  const episodeStart = chart.episode_window.split(" to ")[0] ?? "";
  const episodeEnd = chart.episode_window.split(" to ")[1] ?? "";
  const inEpisode = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => row.date >= episodeStart && row.date <= episodeEnd)
    .map(({ index }) => index);
  const windowFrom = inEpisode.length > 0 ? x(inEpisode[0] ?? 0) : null;
  const windowTo = inEpisode.length > 0 ? x(inEpisode[inEpisode.length - 1] ?? 0) : null;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => top * fraction);

  return (
    <figure style={{ margin: 0 }}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        role="img"
        aria-label={`Oil rate against expectation, ${chart.episode_window}`}
      >
        {ticks.map((value) => (
          <g key={value}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--steel-100)"
            />
            <text x={PAD.left - 8} y={y(value) + 4} textAnchor="end" fontSize="10" fill="var(--steel-600)">
              {Math.round(value)}
            </text>
          </g>
        ))}

        {windowFrom !== null && windowTo !== null ? (
          <rect
            x={windowFrom}
            y={PAD.top}
            width={Math.max(windowTo - windowFrom, 1)}
            height={plotHeight}
            fill="var(--amber-100)"
            opacity="0.75"
          />
        ) : null}

        {rows.map((row, index) =>
          row.day_class !== "valid_producing" ? (
            <rect
              key={`downtime-${row.date}`}
              x={x(index) - 1}
              y={PAD.top}
              width={2}
              height={plotHeight}
              fill="var(--steel-200)"
            />
          ) : null,
        )}

        {segments(rows).map((segment) => {
          const band = [
            ...segment.rows.map((row, i) => `${x(segment.from + i)},${y(row.upper ?? 0)}`),
            ...segment.rows
              .map((row, i) => `${x(segment.from + i)},${y(row.lower ?? 0)}`)
              .reverse(),
          ].join(" ");
          const expected = segment.rows
            .map((row, i) => `${x(segment.from + i)},${y(row.expected ?? 0)}`)
            .join(" ");
          return (
            <g key={`segment-${segment.from}`}>
              <polygon points={band} fill="var(--steel-400)" opacity="0.18" />
              <polyline
                points={expected}
                fill="none"
                stroke="var(--steel-600)"
                strokeWidth="1.4"
                strokeDasharray="5 3"
              />
            </g>
          );
        })}

        <polyline
          points={rows
            .map((row, index) => (row.actual === null ? null : `${x(index)},${y(row.actual)}`))
            .filter((point): point is string => point !== null)
            .join(" ")}
          fill="none"
          stroke="var(--steel-950)"
          strokeWidth="1.6"
        />

        {rows.map((row, index) =>
          row.below_band && row.actual !== null ? (
            <circle
              key={`below-${row.date}`}
              cx={x(index)}
              cy={y(row.actual)}
              r="1.9"
              fill="var(--contradicts)"
            />
          ) : null,
        )}

        <text x={PAD.left} y={HEIGHT - 8} fontSize="10" fill="var(--steel-600)">
          {rows[0]?.date}
        </text>
        <text x={WIDTH - PAD.right} y={HEIGHT - 8} textAnchor="end" fontSize="10" fill="var(--steel-600)">
          {rows[rows.length - 1]?.date}
        </text>
      </svg>
      <figcaption style={{ fontSize: 11.5, color: "var(--steel-600)", marginTop: 6 }}>
        Solid: oil rate, Sm3/d. Dashed with band: the expectation and its interval, from the model
        fitted on the governing reference window ({chart.governing_window}). Amber: the episode
        window. Grey verticals: days that are not valid producing, where the model makes no
        prediction. Red points: days below the lower bound, which is the condition the detector
        opened on.
      </figcaption>
    </figure>
  );
}
