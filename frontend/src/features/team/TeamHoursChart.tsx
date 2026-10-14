import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { formatHours } from '@/features/attendance/formatters'
import type { TeamMemberHoursResponse } from '@/lib/api/types'

/**
 * "Hours by employee" — a grouped bar chart (Today / This week / This month
 * per employee), plain inline SVG rather than a charting dependency (see
 * CLAUDE.md's "no dependency was added" precedent). One hue per **time
 * period**, not per employee — employee identity already comes from the
 * x-axis position/label, so coloring by employee here would encode the same
 * information twice and cost a legend for no benefit.
 *
 * The three series colors are the `dataviz` skill's validated default
 * categorical palette (`node scripts/validate_palette.js` — passes
 * lightness/chroma/CVD-separation/normal-vision on both this app's light
 * surface, `#faf9f5`, and its dark surface; the aqua slot WARNs below 3:1
 * contrast on the light surface). Relief for that WARN is the hover title
 * on every bar plus `TeamHoursTable` below this chart, not a label on
 * every bar — only each group's tallest bar gets a direct label (labeling
 * all three collided the moment two were close in value, confirmed on a
 * real render before this was narrowed) — color is never the only way to
 * read a value here.
 * Deliberately NOT drawn from the app's own role/brand hues (accent/
 * manager/admin/employee): those encode role identity in UI chrome, a
 * different job from time-period identity in a chart, and reusing one here
 * would misleadingly suggest the chart is about roles.
 */

const SERIES = [
  { key: 'today_hours', label: 'Today', light: '#2a78d6', dark: '#3987e5' },
  { key: 'week_hours', label: 'This week', light: '#eb6834', dark: '#d95926' },
  { key: 'month_hours', label: 'This month', light: '#1baf7a', dark: '#199e70' },
] as const

const VIEW_WIDTH = 640
const VIEW_HEIGHT = 240
const PADDING = { top: 12, right: 12, bottom: 28, left: 8 }
const BAR_RADIUS = 3
const BAR_GAP = 3
const GROUP_GAP = 20

/** A clean, round axis ceiling above the highest value — never the raw max
 * (which would put a bar flush against the top edge with no headroom). */
function niceCeiling(max: number): number {
  if (max <= 0) return 4
  const rawStep = max / 4
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude
  return Math.ceil(max / step) * step
}

/** A bar with rounded top corners and a square baseline — `rx` on a plain
 * `<rect>` would round all four corners, so this is a small path instead. */
function roundedTopBarPath(x: number, y: number, width: number, height: number, radius: number): string {
  const r = Math.max(0, Math.min(radius, width / 2, height))
  const bottom = y + height
  return `M${x},${bottom} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + width - r},${y} Q${x + width},${y} ${x + width},${y + r} L${x + width},${bottom} Z`
}

export function TeamHoursChart({ employees }: { employees: TeamMemberHoursResponse[] }) {
  if (employees.length === 0) return null

  const plotWidth = VIEW_WIDTH - PADDING.left - PADDING.right
  const plotHeight = VIEW_HEIGHT - PADDING.top - PADDING.bottom
  const groupWidth = plotWidth / employees.length
  const barWidth = Math.min(24, (groupWidth - GROUP_GAP - BAR_GAP * (SERIES.length - 1)) / SERIES.length)

  const maxValue = Math.max(0, ...employees.flatMap((e) => SERIES.map((s) => e[s.key])))
  const yMax = niceCeiling(maxValue)
  const yTicks = [0, yMax / 4, yMax / 2, (yMax * 3) / 4, yMax]

  function yFor(value: number): number {
    return PADDING.top + plotHeight - (value / yMax) * plotHeight
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>By employee</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Legend — always visible for 2+ series, a colored swatch beside
         * each label so identity never rests on color alone. */}
        <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1">
          {SERIES.map((series) => (
            <span key={series.key} className="flex items-center gap-1.5 text-xs text-foreground-muted">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-full"
                style={{ backgroundColor: `var(--chart-color-${series.key.split('_')[0]})` }}
              />
              {series.label}
            </span>
          ))}
        </div>

        <svg
          viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
          role="img"
          aria-label={`Hours by employee: ${employees
            .map((e) => `${e.name} — today ${formatHours(e.today_hours)}, this week ${formatHours(e.week_hours)}, this month ${formatHours(e.month_hours)}`)
            .join('; ')}`}
          className="w-full"
        >
          {/* Recessive hairline gridlines — never competing with the data. */}
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={PADDING.left}
                x2={VIEW_WIDTH - PADDING.right}
                y1={yFor(tick)}
                y2={yFor(tick)}
                stroke="var(--border)"
                strokeWidth={1}
              />
              <text x={PADDING.left} y={yFor(tick) - 4} fontSize={9} fill="var(--foreground-muted)">
                {formatHours(tick)}
              </text>
            </g>
          ))}

          {employees.map((employee, groupIndex) => {
            const groupX = PADDING.left + groupIndex * groupWidth + (groupWidth - (barWidth * SERIES.length + BAR_GAP * (SERIES.length - 1))) / 2
            // Label only the group's tallest bar — three adjacent labels on
            // three adjacent bars collide the moment two are close in value
            // (measured, not assumed: this is exactly what happened on a
            // real render before this fix). The legend, the hover title,
            // and the breakdown table below carry the other two values.
            const tallestValue = Math.max(...SERIES.map((series) => employee[series.key]))
            const tallestIndex = SERIES.findIndex((series) => employee[series.key] === tallestValue)
            return (
              <g key={employee.user_id}>
                {SERIES.map((series, seriesIndex) => {
                  const value = employee[series.key]
                  const barHeight = (value / yMax) * plotHeight
                  const x = groupX + seriesIndex * (barWidth + BAR_GAP)
                  const y = yFor(value)
                  return (
                    <g key={series.key}>
                      <path d={roundedTopBarPath(x, y, barWidth, barHeight, BAR_RADIUS)} fill={`var(--chart-color-${series.key.split('_')[0]})`}>
                        <title>
                          {employee.name} — {series.label}: {formatHours(value)}
                        </title>
                      </path>
                      {value > 0 && seriesIndex === tallestIndex && (
                        <text
                          x={x + barWidth / 2}
                          y={y - 3}
                          textAnchor="middle"
                          fontSize={8}
                          fill="var(--foreground-muted)"
                        >
                          {formatHours(value)}
                        </text>
                      )}
                    </g>
                  )
                })}
                <text
                  x={groupX + (barWidth * SERIES.length + BAR_GAP * (SERIES.length - 1)) / 2}
                  y={VIEW_HEIGHT - PADDING.bottom + 16}
                  textAnchor="middle"
                  fontSize={10}
                  fill="var(--foreground-muted)"
                >
                  {employee.name.split(' ')[0]}
                </text>
              </g>
            )
          })}
        </svg>
      </CardContent>
    </Card>
  )
}
