import { useEffect, useState } from 'react'
import { api } from './api'
import { ScheduleData } from './schedule-data'

type Period = { grace: string; days: string }
type Row = { period: number; day: number; opening: string; interest: string; payment: string; capital: string;
  closing: string; tea: string; rate_percent: string; late_percent: string; penalty: string; total: string }
type Result = { principal: string; price: string; initial: string; initial_percent: string; months: number;
  period_days: number; late_tea: string; sale_total: string; interest: string; penalty: string; rows: Row[] }
const standard = { grace: 'normal', days: '0' }
const cashFields = ['opening', 'interest', 'payment', 'capital', 'closing'] as const
type Example = { price: string; initial: string; tea: string; lateTea: string; months: string;
  change: { period: string; tea: string } | null; edits: Record<number, Period> }
const examples = {
  bodega: { price: '400', initial: '50', tea: '24', lateTea: '30', months: '3',
    change: { period: '4', tea: '20' }, edits: {0: {grace: 'total', days: '0'}, 3: {grace: 'normal', days: '3'}} },
  parcial: { price: '500', initial: '150', tea: '25', lateTea: '60', months: '2',
    change: null, edits: {0: {grace: 'partial', days: '0'}, 1: {grace: 'normal', days: '5'}} },
  puntual: { price: '240', initial: '40', tea: '18', lateTea: '30', months: '1',
    change: null, edits: {} },
} satisfies Record<string, Example>

function Summary({ result }: { result: Result }) {
  const rows = result.rows
  const balances = [Number(result.principal), ...rows.map(row => Number(row.closing))]
  const peak = Math.max(...balances, 0.01)
  const path = balances.map((balance, i) => (4 + i * 392 / rows.length) + ',' + (96 - 92 * balance / peak)).join(' ')
  const largest = Math.max(...rows.map(row => Number(row.payment)), 0.01)
  return <section className="stack"><h2>Resumen del préstamo</h2>
    <div className="fields">{[['Monto financiado', result.principal], ['Total de intereses', result.interest],
      ['Total de mora', result.penalty], ['Total con inicial y mora', result.sale_total]].map(([label, value]) =>
      <div className="panel metric" key={label}><p>{label}</p><strong>S/ {value}</strong></div>)}
      <div className="panel metric"><p>Tasa de 15 días{rows[0].tea !== rows.at(-1)?.tea && ' inicial'}</p>
        <strong>{rows[0].rate_percent} %</strong></div></div>
    <div className="fields"><figure className="panel sim-chart"><figcaption>Evolución del saldo</figcaption>
      <svg viewBox="0 0 400 100" role="img" aria-label="Saldo por periodo, desde el desembolso hasta la última cuota">
        <path d="M4 96H396" stroke="#aab8af"/><polyline points={path} fill="none" stroke="#245c49" strokeWidth="3"/></svg>
      <small>Del desembolso al periodo {rows.length} · máximo S/ {peak.toFixed(2)}</small></figure>
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
  const [initial, setInitial] = useState('0')
  const [tea, setTea] = useState('25')
  const [changeEnabled, setChangeEnabled] = useState(false)
  const [newTea, setNewTea] = useState('20')
  const [changePeriod, setChangePeriod] = useState('4')
  const [lateTea, setLateTea] = useState('60')
  const [months, setMonths] = useState('3')
  const [edits, setEdits] = useState<Record<number, Period>>({})
  const [answer, setAnswer] = useState<{ key: string; result?: Result; error?: string }>()
  const validMonths = /^\d+$/.test(months) && Number(months) >= 1 && Number(months) <= 120
  const periods = Array.from({ length: validMonths ? Number(months)*2 : 0 }, (_, i) => edits[i] ?? standard)
  let error = ''
  const rateInputs = [['La TEA', tea, 7], ['La TEA de mora', lateTea, 7]] as const
  for (const [label, value, decimals] of [...rateInputs, ['El precio', principal, 2],
    ...(changeEnabled ? [['La nueva TEA', newTea, 7] as const] : [])] as const) {
    if (!/^\d{1,16}(\.\d+)?$/.test(value) || Number(value) <= 0 || (value.split('.')[1]?.length ?? 0) > decimals) {
      error = label + ' debe ser mayor que cero (hasta 16 dígitos enteros y ' + decimals + ' decimales).'
      break
    }
  }
  if (!error && !validMonths) error = 'El plazo debe ser un entero de 1 a 120 meses.'
  if (!error && !/^\d{1,16}(\.\d{1,2})?$/.test(initial)) error = 'Ingresa una inicial de cero o más, con hasta dos decimales.'
  if (!error && changeEnabled && (!/^\d+$/.test(changePeriod) || Number(changePeriod) < 2 || Number(changePeriod) > periods.length)) {
    error = 'El cambio de TEA debe empezar entre la segunda y la última cuota.'
  }
  if (!error && periods.every(row => row.grace !== 'normal')) error = 'Al menos un periodo debe quedar sin gracia.'
  if (!error && periods.some(row => !/^\d+$/.test(row.days) || !Number.isSafeInteger(Number(row.days)))) {
    error = 'Los días de demora deben ser enteros mayores o iguales a cero.'
  }
  const key = JSON.stringify({ principal, initial, tea, late_tea: lateTea, months: Number(months),
    rate_change: changeEnabled ? { period: Number(changePeriod), tea: newTea } : null,
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
  function loadExample(example: Example) {
    setPrincipal(example.price)
    setInitial(example.initial)
    setTea(example.tea)
    setLateTea(example.lateTea)
    setMonths(example.months)
    setChangeEnabled(example.change !== null)
    setChangePeriod(example.change?.period ?? '2')
    setNewTea(example.change?.tea ?? '20')
    setEdits(example.edits)
  }
  return <><h1>Simulador de préstamos</h1>
    <section className="panel stack"><h2>Datos de la venta</h2>
      <div className="actions">
        <button className="secondary" type="button" onClick={() => loadExample(examples.bodega)}>Cargar ejemplo de bodega</button>
        <button className="secondary" type="button" onClick={() => loadExample(examples.parcial)}>Gracia parcial y atraso</button>
        <button className="secondary" type="button" onClick={() => loadExample(examples.puntual)}>Pago puntual</button>
      </div>
    <div className="fields">
      <label>Precio de venta (S/)<input type="number" step="0.01" value={principal} onChange={e=>setPrincipal(e.target.value)}/></label>
      <label>Cuota inicial (S/)<input type="number" min="0" step="0.01" value={initial} onChange={e=>setInitial(e.target.value)}/></label>
      <div className="stack sim-field"><label>TEA (%)<input type="number" step="any" value={tea} aria-describedby="sim-tea-help"
        onChange={e=>setTea(e.target.value)}/></label><small id="sim-tea-help">Interés anual del crédito. Escribe 24 para 24 %.</small></div>
      <label>TEA de mora (%)<input type="number" step="any" value={lateTea} onChange={e=>setLateTea(e.target.value)}/></label>
      <label>Plazo en meses<input type="number" min="1" max="120" value={months} onChange={e=>setMonths(e.target.value)}/></label>
    </div><p>Pago cada 15 días · {periods.length} periodos · Año comercial de 360 días
      {result && <> · <strong>Monto a financiar: S/ {result.principal}</strong></>}</p>
      <label className="check"><input type="checkbox" checked={changeEnabled} onChange={e=>setChangeEnabled(e.target.checked)}/> Cambiar la TEA más adelante</label>
      {changeEnabled && <div className="fields">
        <label>Desde el periodo<input type="number" min="2" max={periods.length} value={changePeriod} onChange={e=>setChangePeriod(e.target.value)}/></label>
        <label>Nueva TEA (%)<input type="number" step="any" value={newTea} onChange={e=>setNewTea(e.target.value)}/></label>
      </div>}
    </section>
    <section className="panel stack"><h2>Cronograma simulado</h2>
      {result && <ScheduleData entries={[
        ['Precio de venta', 'S/ ' + result.price],
        ['Cuota inicial', 'S/ ' + result.initial + ' (' + result.initial_percent + ' %)'],
        ['Préstamo', 'S/ ' + result.principal],
        ['Frecuencia', 'Cada ' + result.period_days + ' días'],
        ['Plazo', result.months + (result.months === 1 ? ' mes' : ' meses')],
        ['N.º de periodos', String(result.rows.length)],
        ['TEA de mora', result.late_tea + ' %'],
      ]} />}
      <p>La TEP es la tasa efectiva de cada quincena. Con gracia total, el interés se suma al saldo. Con gracia parcial, solo se paga el interés. Ingresa días de demora para simular el atraso de una cuota.</p>
      {message && <p role="alert" className="error">{message}</p>}
      {!message && !result && <small role="status">Calculando…</small>}
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla de cuotas"><table className="sim-table">
        <thead><tr className="sim-groups"><th colSpan={4} scope="colgroup">Condiciones</th><th colSpan={5} scope="colgroup">Plan de pagos (S/)</th><th colSpan={4} scope="colgroup">Simulación de atraso</th></tr>
        <tr>{['Periodo / día','TEA','TEP (15 días)','Plazo de gracia','Saldo inicial','Interés','Cuota','Amortización','Saldo final','Días de demora','Tasa de mora','Mora (S/)','Total a pagar (S/)'].map(t=><th key={t} scope="col">{t}</th>)}</tr></thead>
        <tbody>{periods.map((period,i) => {
          const row = result?.rows[i]
          const changed = row && i > 0 && row.tea !== result?.rows[i-1].tea
          return <tr key={i} className={changed ? 'sim-rate-change' : period.grace !== 'normal' ? 'sim-grace' : undefined}><th scope="row">{i+1} / {(i+1)*15}</th>
            <td>{row ? row.tea + ' %' : '—'}{changed && <small>Nueva tasa</small>}</td>
            <td>{row ? row.rate_percent + ' %' : '—'}</td>
            <td><select aria-label={'Gracia del periodo '+(i+1)} value={period.grace} onChange={e=>edit(i,{grace:e.target.value})}>
              <option value="normal">Sin gracia</option><option value="partial">Parcial</option><option value="total">Total</option></select></td>
            {cashFields.map(field=><td key={field}>{row?.[field] ?? '—'}</td>)}
            <td><input type="number" min="0" step="1" aria-label={'Días de demora del periodo '+(i+1)} value={period.days} onChange={e=>edit(i,{days:e.target.value})}/></td>
            <td>{row ? row.late_percent + ' %' : '—'}</td><td>{row?.penalty ?? '—'}</td><td>{row?.total ?? '—'}</td></tr>
        })}</tbody></table></div>
      <small>Los importes y los totales se redondean por separado a dos decimales al mostrarse.</small>
    </section>{result && <Summary result={result}/>}</>
}
