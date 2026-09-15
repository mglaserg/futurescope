export type Health = {
  ok: boolean
  databento_configured: boolean
  markets: string[]
}

export type CurveRow = {
  raw_symbol?: string
  expiration?: string
  close?: number
  dte?: number
  [key: string]: unknown
}

export type StructureRow = {
  order: number
  structure: string
  position: number
  tenor_label: string
  leg_symbols: string
  canonical_value: number
  time_normalized_value: number
  span_days: number
  canonical_weights: string
  trade_weights: string
}

export type TodayResponse = {
  market: string
  market_name: string
  as_of: string
  curve: CurveRow[]
  structures: Record<string, StructureRow[]>
}

export type MeanReversionSummary = {
  episodes: number
  hits: number
  censored_roll: number
  censored_time: number
  hit_rate: number | null
  hit_rate_ci_low: number | null
  hit_rate_ci_high: number | null
  median_time_to_mean_obs: number | null
  median_time_to_mean_days: number | null
  mean_pnl_price_units: number | null
  median_pnl_price_units: number | null
  mean_mae_price_units: number | null
  mean_mfe_price_units: number | null
}

export type MeanReversionResponse = {
  research_look_id: number | null
  market: string
  structure: string
  order: number
  position: number
  target_mode: 'dynamic_zero' | 'frozen_entry_mean'
  summary: MeanReversionSummary
  episodes: Array<Record<string, unknown>>
  survival: Array<{ duration_obs: number; at_risk: number; events: number; censored: number; survival: number }>
  history: Array<{ snapshot_date: string; value: number; canonical_value: number; signal_zscore: number | null; leg_symbols: string }>
  note: string
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail ?? response.statusText)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => fetchJson<Health>('/api/health'),
  today: (market: string, asOf: string, refresh = false) =>
    fetchJson<TodayResponse>(`/api/today/${market}?as_of=${asOf}&refresh=${refresh}`),
  meanReversion: (payload: {
    market: string
    order: number
    position: number
    lookback: number
    entry_z: number
    max_horizon: number
    target_mode: 'dynamic_zero' | 'frozen_entry_mean'
    reason: string
  }) =>
    fetchJson<MeanReversionResponse>('/api/research/mean-reversion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
}
