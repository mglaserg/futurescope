import { StrictMode, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query'
import type { EChartsOption } from 'echarts'
import { api, type DataBackfillResponse, type MeanReversionResponse, type StructureRow } from './api'
import { EChart } from './EChart'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

const todayIso = () => new Date().toISOString().slice(0, 10)

function fmt(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

function pct(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function App() {
  const [view, setView] = useState<'today' | 'data' | 'mean'>('today')
  const [market, setMarket] = useState('GC')
  const [asOf, setAsOf] = useState(todayIso())

  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const today = useQuery({
    queryKey: ['today', market, asOf],
    queryFn: () => api.today(market, asOf),
    enabled: view === 'today',
  })

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">FUTURESCOPE · REACT PREVIEW</div>
          <h1>Futurescope</h1>
        </div>
        <div className={`status-pill ${health.data?.databento_configured ? 'ok' : ''}`}>
          <span className="dot" />
          {health.data?.databento_configured
            ? 'Databento ready'
            : health.data?.env_file_detected
              ? 'Databento key missing in .env'
              : '.env not found'}
        </div>
      </header>

      <nav className="segmented" aria-label="Primary">
        <button className={view === 'today' ? 'active' : ''} onClick={() => setView('today')}>Today</button>
        <button className={view === 'data' ? 'active' : ''} onClick={() => setView('data')}>Data</button>
        <button className={view === 'mean' ? 'active' : ''} onClick={() => setView('mean')}>Mean Reversion Lab</button>
      </nav>

      {view === 'today' ? (
        <TodayView market={market} setMarket={setMarket} asOf={asOf} setAsOf={setAsOf} data={today.data} loading={today.isLoading} error={today.error as Error | null} refresh={() => today.refetch()} />
      ) : view === 'data' ? (
        <DataManager market={market} setMarket={setMarket} />
      ) : (
        <MeanReversionLab market={market} setMarket={setMarket} />
      )}
    </div>
  )
}

function TodayView({ market, setMarket, asOf, setAsOf, data, loading, error, refresh }: {
  market: string
  setMarket: (value: string) => void
  asOf: string
  setAsOf: (value: string) => void
  data: Awaited<ReturnType<typeof api.today>> | undefined
  loading: boolean
  error: Error | null
  refresh: () => void
}) {
  const curveOption = useMemo<EChartsOption>(() => ({
    animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: 46, right: 18, top: 24, bottom: 44 },
    xAxis: { type: 'category', data: data?.curve.map((row) => String(row.raw_symbol ?? '')) ?? [], axisLabel: { rotate: 25 } },
    yAxis: { type: 'value', scale: true, name: 'Price' },
    series: [{ type: 'line', smooth: true, symbolSize: 7, data: data?.curve.map((row) => Number(row.close ?? 0)) ?? [] }],
  }), [data])

  const rows = data?.structures?.['1'] ?? []
  const refreshMutation = useMutation({ mutationFn: () => api.today(market, asOf, true), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['today', market, asOf] }); queryClient.invalidateQueries({ queryKey: ['dataStatus'] }); refresh() } })
  return (
    <main>
      <section className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">SEE TODAY</div>
          <h2>What is the curve doing right now?</h2>
          <p>Current state first. Historical outcome questions live in the registered Mean Reversion Lab.</p>
        </div>
        <div className="control-card">
          <label>Market<select value={market} onChange={(e) => setMarket(e.target.value)}>{['GC','ES','CL','ZN','VX'].map((m) => <option key={m}>{m}</option>)}</select></label>
          <label>As of<input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label>
          <button className="primary" onClick={() => refreshMutation.mutate()} disabled={refreshMutation.isPending}>{refreshMutation.isPending ? 'Refreshing Databento…' : 'Refresh this date'}</button>
          <small className="muted">Force-refresh bypasses Futurescope's raw Databento request cache for this date.</small>
        </div>
      </section>

      {loading && <div className="notice">Loading current curve…</div>}
      {error && <div className="notice error">{error.message}</div>}
      {data && <>
        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">{data.market}</span><h3>{data.market_name} curve</h3></div><span className="muted">{data.as_of}</span></div>
          <EChart option={curveOption} height={340} />
        </section>
        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">FIRST DIFFERENCE</span><h3>Calendar slope map</h3></div><span className="muted">Positive = backwardation under Futurescope’s long-front convention</span></div>
          <StructureTable rows={rows} />
        </section>
      </>}
    </main>
  )
}

function StructureTable({ rows }: { rows: StructureRow[] }) {
  return <div className="table-wrap"><table><thead><tr><th>Location</th><th>Contracts</th><th>Raw value</th><th>Normalized</th><th>Span</th></tr></thead><tbody>
    {rows.map((row) => <tr key={`${row.order}-${row.position}`}><td>{row.tenor_label}</td><td>{row.leg_symbols}</td><td>{fmt(row.canonical_value, 4)}</td><td>{fmt(row.time_normalized_value, 4)}</td><td>{fmt(row.span_days, 0)}d</td></tr>)}
  </tbody></table></div>
}

function DataManager({ market, setMarket }: { market: string; setMarket: (value: string) => void }) {
  const ninetyDaysAgo = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10)
  const [start, setStart] = useState(ninetyDaysAgo)
  const [end, setEnd] = useState(todayIso())
  const [sampling, setSampling] = useState<'business_daily' | 'weekly' | 'month_end'>('business_daily')
  const [forceRefresh, setForceRefresh] = useState(false)
  const status = useQuery({ queryKey: ['dataStatus'], queryFn: api.dataStatus })
  const mutation = useMutation({
    mutationFn: api.backfill,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dataStatus'] })
      queryClient.invalidateQueries({ queryKey: ['today'] })
    },
  })
  const selected = status.data?.markets.find((row) => row.market === market)
  const result: DataBackfillResponse | undefined = mutation.data

  const run = () => mutation.mutate({ market, start, end, sampling, force_refresh: forceRefresh })
  return <main>
    <section className="hero-grid">
      <div className="hero-copy">
        <div className="eyebrow">DATA · DATABENTO</div>
        <h2>Build the history Futurescope can actually research.</h2>
        <p>Backfill local curve snapshots for the Mean Reversion Lab. Existing snapshots and raw Databento request-cache files are reused unless you explicitly force a redownload.</p>
      </div>
      <div className="control-card dense">
        <label>Market<select value={market} onChange={(e) => setMarket(e.target.value)}>{['GC','ES','CL','ZN','VX'].map((m) => <option key={m}>{m}</option>)}</select></label>
        <div className="control-row"><label>Start<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label><label>End<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label></div>
        <label>Sampling<select value={sampling} onChange={(e) => setSampling(e.target.value as typeof sampling)}><option value="business_daily">Business daily</option><option value="weekly">Weekly</option><option value="month_end">Month end</option></select></label>
        <label className="check-row"><input type="checkbox" checked={forceRefresh} onChange={(e) => setForceRefresh(e.target.checked)} /> Force redownload raw Databento requests</label>
        <button className="primary" onClick={run} disabled={mutation.isPending || !start || !end}>{mutation.isPending ? 'Downloading history…' : 'Backfill curve history'}</button>
        <small className="muted">Maximum 260 selected snapshot dates per batch. Current-day requests are automatically clipped to Databento's latest schema availability. Split longer daily histories into multiple ranges.</small>
      </div>
    </section>

    <section className="metrics-grid data-metrics">
      <Metric label={`${market} snapshots`} value={String(selected?.snapshots ?? 0)} sub={selected?.first_snapshot ? `${selected.first_snapshot} → ${selected.last_snapshot}` : 'No local history yet'} />
      <Metric label="Raw cache" value={forceRefresh ? 'Bypass' : 'Reuse'} sub="Definitions + OHLCV-1d" />
      <Metric label="Research source" value="Local snapshots" sub="Mean Reversion Lab reads this cache" />
    </section>

    {mutation.error && <div className="notice error">{(mutation.error as Error).message}</div>}
    {result && <section className="panel">
      <div className="panel-heading"><div><span className="eyebrow">BACKFILL COMPLETE</span><h3>{result.market} curve history</h3></div><span className="muted">{result.start} → {result.end}</span></div>
      <div className="metrics-grid data-metrics">
        <Metric label="Requested" value={String(result.requested)} sub={result.sampling.replace('_', ' ')} />
        <Metric label="Downloaded" value={String(result.downloaded)} sub="new/refreshed snapshots" />
        <Metric label="Reused" value={String(result.skipped_cached)} sub="already cached" />
        <Metric label="Failures" value={String(result.failures.length)} sub={result.failures.length ? 'See details below' : 'clean batch'} />
      </div>
      {result.failures.length > 0 && <div className="notice error">{result.failures.slice(0, 10).map((failure) => <div key={failure.date}>{failure.date}: {failure.error}</div>)}</div>}
      <div className="notice">{result.note}</div>
    </section>}

    <section className="panel">
      <div className="panel-heading"><div><span className="eyebrow">CACHE INVENTORY</span><h3>What Futurescope has locally</h3></div></div>
      <div className="table-wrap"><table><thead><tr><th>Market</th><th>Snapshots</th><th>First</th><th>Last</th></tr></thead><tbody>{status.data?.markets.map((row) => <tr key={row.market}><td>{row.market}</td><td>{row.snapshots}</td><td>{row.first_snapshot ?? '—'}</td><td>{row.last_snapshot ?? '—'}</td></tr>)}</tbody></table></div>
    </section>
  </main>
}

function MeanReversionLab({ market, setMarket }: { market: string; setMarket: (value: string) => void }) {
  const [order, setOrder] = useState(1)
  const [position, setPosition] = useState(1)
  const [lookback, setLookback] = useState(20)
  const [entryZ, setEntryZ] = useState(2)
  const [horizon, setHorizon] = useState(20)
  const [targetMode, setTargetMode] = useState<'dynamic_zero' | 'frozen_entry_mean'>('frozen_entry_mean')
  const [reason, setReason] = useState('Test first passage from registered extreme z-score back to the mean')
  const mutation = useMutation({ mutationFn: api.meanReversion })
  const result = mutation.data

  const zOption = useMemo<EChartsOption>(() => ({
    animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 22, top: 25, bottom: 48 },
    xAxis: { type: 'category', data: result?.history.map((row) => row.snapshot_date.slice(0, 10)) ?? [], axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', name: 'z-score' },
    series: [{
      type: 'line', showSymbol: false, data: result?.history.map((row) => row.signal_zscore) ?? [],
      markLine: { silent: true, data: [{ yAxis: entryZ }, { yAxis: 0 }, { yAxis: -entryZ }] },
    }],
  }), [result, entryZ])

  const survivalOption = useMemo<EChartsOption>(() => ({
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (value) => `${(Number(value) * 100).toFixed(1)}%` },
    grid: { left: 55, right: 22, top: 25, bottom: 48 },
    xAxis: { type: 'value', minInterval: 1, name: 'Observations since entry' },
    yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` }, name: 'Not yet reverted' },
    series: [{ type: 'line', step: 'end', symbolSize: 6, data: result?.survival.map((row) => [row.duration_obs, row.survival]) ?? [] }],
  }), [result])

  const run = () => mutation.mutate({ market, order, position, lookback, entry_z: entryZ, max_horizon: horizon, target_mode: targetMode, reason })
  return <main>
    <section className="hero-grid">
      <div className="hero-copy"><div className="eyebrow">PROVE IT · REGISTERED LOOK</div><h2>Does the spread actually come back?</h2><p>An episode starts when z crosses an extreme threshold. We measure first passage back to the mean, not just whether an ADF test likes the series.</p></div>
      <div className="control-card dense">
        <div className="control-row"><label>Market<select value={market} onChange={(e) => setMarket(e.target.value)}>{['GC','ES','CL','ZN','VX'].map((m) => <option key={m}>{m}</option>)}</select></label><label>Structure<select value={order} onChange={(e) => setOrder(Number(e.target.value))}><option value={1}>Slope</option><option value={2}>Butterfly</option><option value={3}>Double butterfly</option></select></label></div>
        <div className="control-row"><label>Curve slot<input type="number" min={1} value={position} onChange={(e) => setPosition(Number(e.target.value))}/></label><label>Lookback<input type="number" min={3} value={lookback} onChange={(e) => setLookback(Number(e.target.value))}/></label></div>
        <div className="control-row"><label>Entry |z|<input type="number" min={0.5} step={0.25} value={entryZ} onChange={(e) => setEntryZ(Number(e.target.value))}/></label><label>Max horizon<input type="number" min={1} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}/></label></div>
        <label>Mean target<select value={targetMode} onChange={(e) => setTargetMode(e.target.value as typeof targetMode)}><option value="frozen_entry_mean">Frozen entry mean</option><option value="dynamic_zero">Dynamic z = 0</option></select></label>
        <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button className="primary" onClick={run} disabled={mutation.isPending}>{mutation.isPending ? 'Running…' : 'Log + run analysis'}</button>
      </div>
    </section>

    {mutation.error && <div className="notice error">{(mutation.error as Error).message}</div>}
    {result && <MeanReversionResult result={result} zOption={zOption} survivalOption={survivalOption} />}
  </main>
}

function MeanReversionResult({ result, zOption, survivalOption }: { result: MeanReversionResponse; zOption: EChartsOption; survivalOption: EChartsOption }) {
  const s = result.summary
  return <>
    <div className="registry-note">Research look #{result.research_look_id ?? 'logging failed'} · {result.structure} · {result.target_mode === 'frozen_entry_mean' ? 'frozen entry mean' : 'dynamic z=0'}</div>
    <section className="metrics-grid">
      <Metric label="Episodes" value={String(s.episodes)} sub={`${s.hits} hit mean`} />
      <Metric label="Hit rate" value={pct(s.hit_rate)} sub={s.hit_rate_ci_low == null ? 'No interval' : `95% Wilson ${pct(s.hit_rate_ci_low)}–${pct(s.hit_rate_ci_high)}`} />
      <Metric label="Median time" value={s.median_time_to_mean_obs == null ? '—' : `${fmt(s.median_time_to_mean_obs, 1)} obs`} sub={s.median_time_to_mean_days == null ? '—' : `${fmt(s.median_time_to_mean_days, 1)} calendar days`} />
      <Metric label="Mean P&L" value={fmt(s.mean_pnl_price_units, 3)} sub="canonical price units" />
      <Metric label="Mean MAE" value={fmt(s.mean_mae_price_units, 3)} sub="before exit/censor" />
      <Metric label="Mean MFE" value={fmt(s.mean_mfe_price_units, 3)} sub="before exit/censor" />
    </section>
    <section className="split-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">STATE PATH</span><h3>Z-score history</h3></div></div><EChart option={zOption} /></div><div className="panel"><div className="panel-heading"><div><span className="eyebrow">FIRST PASSAGE</span><h3>Probability not yet back to mean</h3></div></div><EChart option={survivalOption} /></div></section>
    <section className="panel"><div className="panel-heading"><div><span className="eyebrow">EPISODES</span><h3>Every threshold crossing</h3></div><span className="muted">Rolls and time stops are censored, not called failures of execution P&L.</span></div><EpisodeTable rows={result.episodes} /></section>
    <div className="notice">{result.note}</div>
  </>
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>
}

function EpisodeTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  return <div className="table-wrap"><table><thead><tr><th>Entry</th><th>Side</th><th>z</th><th>Status</th><th>Duration</th><th>P&L</th><th>MAE</th><th>MFE</th></tr></thead><tbody>{rows.map((row, idx) => <tr key={idx}><td>{String(row.entry_date ?? '').slice(0,10)}</td><td>{String(row.trade_direction ?? '')}</td><td>{fmt(Number(row.entry_zscore),2)}</td><td><span className={`tag ${row.status === 'HIT_MEAN' ? 'good' : ''}`}>{String(row.status ?? '')}</span></td><td>{row.duration_obs as number} obs</td><td>{fmt(Number(row.pnl_price_units),3)}</td><td>{fmt(Number(row.mae_price_units),3)}</td><td>{fmt(Number(row.mfe_price_units),3)}</td></tr>)}</tbody></table></div>
}

createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queryClient}><App /></QueryClientProvider></StrictMode>)
