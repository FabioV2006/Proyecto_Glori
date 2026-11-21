import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, formValues } from './api'
import type { Client, Product } from './catalog'

type Line = { product_id: number; quantity: number }
type SaleInput = { client_id: number; mode: string; months: number; lines: Line[]; sold_at?: string }
type Installment = { sequence: number; due: string; opening: string; interest: string; capital: string; amount: string; closing: string; paid?: boolean }
type Quote = {
  id?: number; mode: string; capital: string; reference_due: string; currency: string
  financed_principal: string; grace_days: number; grace_interest: string; single_interest: string
  interest_days: number; credit_available: string; expected?: unknown; installments: Installment[]
}

function ScheduleTable({ installments, showPayment = false }: { installments: Installment[]; showPayment?: boolean }) {
  return <div className="table-wrap"><table>
    <thead><tr><th>Cuota</th><th>Vencimiento</th><th>Saldo inicial</th><th>Interés</th><th>Amortización</th><th>Pago</th><th>Saldo final</th>{showPayment && <th>Estado</th>}</tr></thead>
    <tbody>{installments.map(row => <tr key={row.sequence}><td>{row.sequence}</td><td>{row.due}</td>
      <td>{row.opening}</td><td>{row.interest}</td><td>{row.capital}</td><td>{row.amount}</td><td>{row.closing}</td>
      {showPayment && <td>{row.amount === '0.00' ? 'Sin obligación' : row.paid ? 'Pagada' : 'Pendiente'}</td>}
    </tr>)}</tbody>
  </table></div>
}

export function NewSale({ demo }: { demo: boolean }) {
  const [clients, setClients] = useState<Client[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [mode, setMode] = useState('single')
  const [lines, setLines] = useState<Line[]>([{ product_id: 0, quantity: 1 }])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<Quote>()
  const [input, setInput] = useState<SaleInput>()
  useEffect(() => {
    void Promise.all([api<Client[]>('/clients'), api<Product[]>('/products')]).then(([c, p]) => {
      setClients(c.filter(row => row.active))
      setProducts(p.filter(row => row.active))
    }).catch(failure => setError(failure.message))
  }, [])
  const allowed = products.filter(product => mode === 'single' ? product.single_allowed : product.monthly_allowed)
  const changeLine = (index: number, changes: Partial<Line>) => setLines(rows =>
    rows.map((row, i) => i === index ? { ...row, ...changes } : row))

  async function requestPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = formValues(event.currentTarget)
    const payload = { client_id: Number(values.client_id), mode, months: Number(values.months), lines,
      ...(values.sold_at ? { sold_at: String(values.sold_at) } : {}) }
    setBusy(true)
    setError('')
    setPreview(undefined)
    try {
      setPreview(await api<Quote>('/sales/preview', 'POST', payload))
      setInput(payload)
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }
  async function confirm() {
    if (!input || !preview) return
    setBusy(true)
    setError('')
    try {
      setPreview(await api<Quote>('/sales', 'POST', { ...input, expected: preview.expected }))
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <h1>Nueva venta</h1>
    {error && <p className="error" role="alert">{error}</p>}
    <form className="stack panel" onChange={() => setPreview(undefined)} onSubmit={requestPreview}>
      <div className="fields">
        <label>Cliente<select name="client_id" required><option value="">Selecciona un cliente</option>
          {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
        <label>Modalidad<select value={mode} onChange={event => {
          setMode(event.target.value)
          setLines([{ product_id: 0, quantity: 1 }])
        }}><option value="single">Pago único por ciclo</option><option value="monthly">Francés mensual</option></select></label>
        {mode === 'monthly' && <label>Cuotas mensuales<input type="number" name="months" min={1} defaultValue={3} required />
          <small>El plazo debe respetar el máximo del cliente.</small></label>}
        {demo && <label>Fecha y hora de compra para demo<input name="sold_at" placeholder="2026-09-15T12:00:00-05:00" />
          <small>Formato ISO con desplazamiento horario. En blanco se toma la hora actual.</small></label>}
      </div>
      {lines.map((line, index) => <div className="fields" key={index}>
        <label>Ítem {index + 1}<select name={'product_' + index} required value={line.product_id || ''} onChange={event => changeLine(index, { product_id: Number(event.target.value) })}>
          <option value="">Selecciona un ítem</option>
          {allowed.map(product => <option key={product.id} value={product.id}>{product.name} · {product.currency} {product.credit_price}</option>)}
        </select></label>
        <label>Cantidad {index + 1}<input type="number" min={1} required value={line.quantity || ''} onChange={e => changeLine(index, { quantity: Number(e.target.value) })} /></label>
        {lines.length > 1 && <div className="actions"><button type="button" className="secondary" onClick={() => {
          setLines(rows => rows.filter((_, i) => i !== index))
          setPreview(undefined)
        }}>Quitar ítem {index + 1}</button></div>}
      </div>)}
      <div className="actions"><button disabled={busy}>Previsualizar</button>
        <button type="button" className="secondary" onClick={() => {
          setLines(rows => [...rows, { product_id: 0, quantity: 1 }])
          setPreview(undefined)
        }}>Agregar ítem</button></div>
    </form>
    {preview && <section className="stack panel">
      <h2>{preview.id ? 'Venta registrada #' + preview.id : 'Detalle del financiamiento'}</h2>
      <div className="fields"><p>Capital · {preview.currency} {preview.capital}</p>
        <p>Crédito disponible · {preview.currency} {preview.credit_available}</p>
        <p>{preview.mode === 'single' ? 'Vencimiento' : 'Fin de gracia'} · {preview.reference_due}</p>
        {preview.mode === 'monthly' ? <>
          <p>Gracia inicial · {preview.grace_days} días</p><p>Interés capitalizado · {preview.grace_interest}</p>
          <p>Capital después de la gracia · {preview.financed_principal}</p>
        </> : <p>Interés compensatorio · {preview.single_interest} ({preview.interest_days} días)</p>}
      </div>
      {!!preview.installments.length && <ScheduleTable installments={preview.installments} />}
      {!preview.id && <div><button onClick={() => void confirm()} disabled={busy}>Confirmar venta</button></div>}
    </section>}
  </>
}

type SavedSchedule = {
  id: number; currency: string; capital: string; principal_pending: string
  grace_days: number; grace_interest: string; installments: Installment[]
}

export function Schedules() {
  const [clients, setClients] = useState<Client[]>([])
  const [results, setResults] = useState<SavedSchedule[]>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    void api<Client[]>('/clients').then(setClients).catch(failure => setError(failure.message))
  }, [])
  async function consult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const client = formValues(event.currentTarget).client
    setError('')
    setResults(undefined)
    setBusy(true)
    try {
      setResults(await api<SavedSchedule[]>('/clients/' + client + '/schedules'))
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <h1>Cronogramas</h1>
    {error && <p className="error" role="alert">{error}</p>}
    <form className="panel stack" onSubmit={consult} onChange={() => setResults(undefined)}>
      <label>Cliente<select name="client" required><option value="">Selecciona un cliente</option>
        {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
      </select></label>
      <div><button disabled={busy}>Consultar cronogramas</button></div>
    </form>
    {results?.length === 0 && <p>El cliente aún no tiene ventas financiadas en cuotas.</p>}
    {results?.map(row => <section className="panel stack" key={row.id}>
      <h2>Venta #{row.id}</h2>
      <div className="fields"><p>Capital original · {row.currency} {row.capital}</p>
        <p>Gracia · {row.grace_days} días, {row.currency} {row.grace_interest} capitalizados</p>
        <p>Capital pendiente · {row.currency} {row.principal_pending}</p>
      </div>
      <ScheduleTable installments={row.installments} showPayment />
    </section>)}
  </>
}
