import { useEffect, useState } from 'react'
import { api } from './api'

type Period = { grace: string; days: string }
type Row = { period: number; day: number; opening: string; interest: string; payment: string; capital: string;
  closing: string; late_rate: string; penalty: string; total: string }
type Result = { principal: string; rate: string; interest: string; total: string; penalty: string; rows: Row[] }
const standard = { grace: 'normal', days: '0' }
const cashFields = ['opening', 'interest', 'payment', 'capital', 'closing'] as const

function Summary({ result }: { result: Result }) {
  const rows = result.rows
  const balances = [Number(result.principal), ...rows.map(row => Number(row.closing))]
  const peak = Math.max(...balances, 0.01)
  const path = balances.map((balance, i) => (4 + i * 392 / rows.length) + ',' + (96 - 92 * balance / peak)).join(' ')
  const largest = Math.max(...rows.map(row => Number(row.payment)), 0.01)
  return <section className="stack"><h2>Resumen del préstamo</h2>
    <div className="fields">{[['Monto prestado', result.principal], ['Total de intereses', result.interest],
      ['Total de mora', result.penalty], ['Total pagado con mora', result.total], ['Tasa efectiva quincenal', result.rate]].map(([label, value]) =>
      <div className="panel metric" key={label}><p>{label}</p><strong>{label.startsWith('Tasa') ? value : 'S/ ' + value}</strong></div>)}</div>
    <div className="fields"><figure className="panel sim-chart"><figcaption>Evolución del saldo</figcaption>
      <svg viewBox="0 0 400 100" role="img" aria-label="Saldo por periodo, desde el desembolso hasta la última cuota">
        <path d="M4 96H396" stroke="#aab8af"/><polyline points={path} fill="none" stroke="#245c49" strokeWidth="3"/></svg>
      <small>Desembolso → periodo {rows.length} · máximo S/ {peak.toFixed(2)}</small></figure>
      <figure className="panel sim-chart"><figcaption>Composición de cada cuota</figcaption>
        <svg viewBox="0 0 400 100" role="img" aria-label="Cuotas por periodo desglosadas en amortización e interés pagado">
          {rows.map((row,i) => {
            const height = 95 * Number(row.payment) / largest
            const principalHeight = Math.min(height, 95 * Number(row.capital) / largest)
            const width = 400 / rows.length
            return <g key={row.period}><title>Periodo {row.period} · cuota S/ {row.payment}</title>
              <rect x={i*width} y={98-height} width={width*.78} height={height} fill="#b6723c"/>
              <rect x={i*width} y={98-principalHeight} width={width*.78} height={principalHeight} fill="#245c49"/></g>
          })}</svg><small className="sim-legend"><span>Amortización</span><span>Interés pagado</span></small></figure></div>
  </section>
}

export function Simulator() {
  const [principal, setPrincipal] = useState('1000')
  const [tea, setTea] = useState('25')
  const [lateTea, setLateTea] = useState('60')
  const [months, setMonths] = useState('3')
  const [edits, setEdits] = useState<Record<number, Period>>({})
  const [answer, setAnswer] = useState<{ key: string; result?: Result; error?: string }>()
  const validMonths = /^\d+$/.test(months) && Number(months) >= 1 && Number(months) <= 120
  const periods = Array.from({ length: validMonths ? Number(months)*2 : 0 }, (_, i) => edits[i] ?? standard)
  let error = ''
  for (const [label, value, decimals] of [['El monto', principal, 16], ['La TEA', tea, 7], ['La TEA de mora', lateTea, 7]] as const) {
    if (!/^\d{1,16}(\.\d+)?$/.test(value) || Number(value) <= 0 || (value.split('.')[1]?.length ?? 0) > decimals) {
      error = label + ' debe ser mayor que cero (hasta 16 dígitos enteros y ' + decimals + ' decimales).'
      break
    }
  }
  if (!error && !validMonths) error = 'El plazo debe ser un entero de 1 a 120 meses.'
  if (!error && periods.every(row => row.grace !== 'normal')) error = 'Al menos un periodo debe quedar sin gracia.'
  if (!error && periods.some(row => !/^\d+$/.test(row.days) || !Number.isSafeInteger(Number(row.days)))) {
    error = 'Los días de demora deben ser enteros mayores o iguales a cero.'
  }
  const key = JSON.stringify({ principal, tea, late_tea: lateTea, months: Number(months),
    periods: periods.map(row => ({ grace: row.grace, days: Number(row.days) })) })
  useEffect(() => {
    if (error) return
    let active = true
    const timer = window.setTimeout(() => {
      api<Result>('/simulator', 'POST', JSON.parse(key)).then(result => {
        if (active) setAnswer({ key, result })
      }).catch(failure => { if (active) setAnswer({ key, error: failure.message }) })
    }, 180)
    return () => { active = false; window.clearTimeout(timer) }
  }, [key, error])
  const current = !error && answer?.key === key ? answer : undefined
  const result = current?.result
  const message = error || current?.error
  function edit(i: number, change: Partial<Period>) {
    setEdits(previous => ({ ...previous, [i]: { ...(previous[i] ?? standard), ...change } }))
  }
  return <><h1>Simulador de préstamos</h1>
    <section className="panel stack"><h2>Condiciones</h2><div className="fields">
      <label>Monto del préstamo (S/)<input type="number" step="any" value={principal} onChange={e=>setPrincipal(e.target.value)}/></label>
      <label>TEA (%)<input type="number" step="any" value={tea} onChange={e=>setTea(e.target.value)}/></label>
      <label>TEA de mora (%)<input type="number" step="any" value={lateTea} onChange={e=>setLateTea(e.target.value)}/></label>
      <label>Plazo en meses<input type="number" min="1" max="120" value={months} onChange={e=>setMonths(e.target.value)}/></label>
    </div><p>Frecuencia fija de 15 días · Mes comercial de 30 días · Base anual de 360 días.</p></section>
    <section className="panel stack"><h2>Cronograma simulado</h2>
      <p>Elige la gracia y los días de demora de cada cuota. Las tasas de la tabla se expresan en fracción decimal.</p>
      {message && <p role="alert" className="error">{message}</p>}
      {!message && !result && <small role="status">Calculando…</small>}
      <div className="table-wrap"><table className="sim-table"><thead><tr>{['Periodo / día','Tasa','Gracia','Saldo inicial','Intereses','Cuota','Amortización','Saldo final','Días de demora','Tasa de mora','Interés moratorio','Total a pagar'].map(t=><th key={t}>{t}</th>)}</tr></thead>
        <tbody>{periods.map((period,i) => {
          const row = result?.rows[i]
          return <tr key={i}><th scope="row">{i+1} / {(i+1)*15}</th><td>{result?.rate ?? '—'}</td>
            <td><select aria-label={'Gracia del periodo '+(i+1)} value={period.grace} onChange={e=>edit(i,{grace:e.target.value})}>
              <option value="normal">Sin gracia</option><option value="partial">Parcial</option><option value="total">Total</option></select></td>
            {cashFields.map(field=><td key={field}>{row?.[field] ?? '—'}</td>)}
            <td><input type="number" min="0" step="1" aria-label={'Días de demora del periodo '+(i+1)} value={period.days} onChange={e=>edit(i,{days:e.target.value})}/></td>
            <td>{row?.late_rate ?? '—'}</td><td>{row?.penalty ?? '—'}</td><td>{row?.total ?? '—'}</td></tr>
        })}</tbody></table></div>
      <small>Los importes y los totales se redondean por separado a dos decimales al mostrarse.</small>
    </section>{result && <Summary result={result}/>}</>
}
