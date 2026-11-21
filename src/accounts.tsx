import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type { Client } from './catalog'

type Sale = { id: number; sold_at: string; reference_due: string; mode: string; capital: string; principal_pending: string; currency: string }
type Purchase = Pick<Sale, 'id' | 'sold_at' | 'mode' | 'capital'> & { single_interest: string; grace_interest: string; items: string }
type Allocation = { kind: 'statement' | 'installment'; id: number; due: string; days_late: number; capital: string; interest: string; mora: string; amount: string }
type Receipt = { id: number; paid_at: string; currency: string; capital: string; interest: string; mora: string; amount: string }
type Statement = {
  id: number; cutoff_at: string; due: string; currency: string; single_capital: string; single_interest: string
  payment_id?: number; purchases: Purchase[]; installments: { id: number; sale_id: number; sequence: number; capital: string; interest: string; amount: string; payment_id?: number }[]
}
type Account = {
  name: string; timezone: string; currency: string; credit_available: string; credit_limit: string
  statements: Statement[]; sales: Sale[]; payments: Receipt[]
  liquidation: Omit<Receipt, 'id' | 'paid_at' | 'currency'> & { rows: Allocation[]; expected: unknown }
}
const money = (currency: string, value: string) => currency + ' ' + value
const modeName = (mode: string) => mode === 'single' ? 'Pago único' : 'Francés mensual'
function local(iso: string, timezone: string) {
  return new Intl.DateTimeFormat('es-PE', { dateStyle: 'short', timeStyle: 'short', timeZone: timezone }).format(new Date(iso))
}

function Summary({ account }: { account: Account }) {
  return <div className="panel stack">
    <h2>{account.name}</h2>
    <div className="fields">
      <p>Límite pactado · {money(account.currency, account.credit_limit)}</p>
      <p>Crédito disponible · {money(account.currency, account.credit_available)}</p>
      <p>Importe exigible · <strong>{money(account.currency, account.liquidation.amount)}</strong></p>
    </div>
  </div>
}

function Statements({ account }: { account: Account }) {
  return <section className="stack">
    <h2>Estados de cuenta al corte</h2>
    {!account.statements.length && <p>Aún no se han emitido estados de cuenta.</p>}
    {account.statements.map(statement => <details className="panel" key={statement.id}>
      <summary>Estado #{statement.id} · Corte {local(statement.cutoff_at, account.timezone)} · Vence {statement.due}</summary>
      <div className="stack statement">
        {statement.single_capital !== '0.00' && <p>Pago único · Capital {money(statement.currency, statement.single_capital)} · Compensatorio {statement.single_interest} · {statement.payment_id ? 'Pagado' : 'Pendiente'}</p>}
        {!!statement.purchases.length && <div className="table-wrap"><table>
          <thead><tr><th>Compra</th><th>Fecha</th><th>Modalidad</th><th>Capital</th><th>Compensatorio</th></tr></thead>
          <tbody>{statement.purchases.map(row => <tr key={row.id}><td>#{row.id} {row.items}</td>
            <td>{local(row.sold_at, account.timezone)}</td><td>{modeName(row.mode)}</td><td>{row.capital}</td>
            <td>{row.mode === 'single' ? row.single_interest : row.grace_interest + ' capitalizado'}</td></tr>)}</tbody>
        </table></div>}
        {!!statement.installments.length && <div className="table-wrap"><table>
          <thead><tr><th>Venta</th><th>Cuota</th><th>Capital</th><th>Compensatorio</th><th>Pago</th><th>Estado</th></tr></thead>
          <tbody>{statement.installments.map(row => <tr key={row.id}><td>#{row.sale_id}</td><td>{row.sequence}</td>
            <td>{row.capital}</td><td>{row.interest}</td><td>{row.amount}</td><td>{row.payment_id ? 'Pagada' : 'Pendiente'}</td></tr>)}</tbody>
        </table></div>}
      </div>
    </details>)}
    {!!account.sales.length && <section className="panel table-wrap"><h2>Historial de ventas</h2><table>
      <thead><tr><th>Venta</th><th>Fecha</th><th>Modalidad</th><th>Capital original</th><th>Capital pendiente</th></tr></thead>
      <tbody>{account.sales.map(row => <tr key={row.id}><td>#{row.id}</td><td>{local(row.sold_at, account.timezone)}</td>
        <td>{modeName(row.mode)}</td><td>{money(row.currency, row.capital)}</td><td>{money(row.currency, row.principal_pending)}</td>
      </tr>)}</tbody>
    </table></section>}
  </section>
}

function Liquidation({ account }: { account: Account }) {
  const due = account.liquidation
  return <section className="panel stack">
    <h2>Liquidación de obligaciones</h2>
    {!due.rows.length ? <p>Sin obligaciones exigibles.</p> : <>
      <div className="table-wrap"><table>
        <thead><tr><th>Obligación</th><th>Vence</th><th>Días de mora</th><th>Mora</th><th>Compensatorio</th><th>Capital</th><th>Exigible</th></tr></thead>
        <tbody>{due.rows.map(row => <tr key={row.kind + row.id}>
          <td>{row.kind === 'statement' ? 'Estado de cuenta' : 'Cuota'} #{row.id}</td><td>{row.due}</td>
          <td>{row.days_late}</td><td>{row.mora}</td><td>{row.interest}</td><td>{row.capital}</td><td>{row.amount}</td>
        </tr>)}</tbody>
      </table></div>
      <p>Mora {due.mora} · Compensatorio {due.interest} · Capital {due.capital} · <strong>Total {due.amount}</strong></p>
    </>}
  </section>
}

function Payments({ account }: { account: Account }) {
  return <section className="panel table-wrap"><h2>Historial de cobros</h2>
    {account.payments.length ? <table>
      <thead><tr><th>Comprobante</th><th>Fecha</th><th>Mora</th><th>Compensatorio</th><th>Capital</th><th>Total</th></tr></thead>
      <tbody>{account.payments.map(row => <tr key={row.id}><td>#{row.id}</td><td>{local(row.paid_at, account.timezone)}</td>
        <td>{row.mora}</td><td>{row.interest}</td><td>{row.capital}</td><td>{money(row.currency, row.amount)}</td>
      </tr>)}</tbody>
    </table> : <p>Aún no hay cobros registrados.</p>}
  </section>
}

export function ShopAccount({ isPayment, demo }: { isPayment: boolean; demo: boolean }) {
  const [clients, setClients] = useState<Client[]>([])
  const [account, setAccount] = useState<Account>()
  const [selection, setSelection] = useState<{ id: string; as_of?: string }>()
  const [error, setError] = useState('')
  const [result, setResult] = useState<Receipt>()
  const [busy, setBusy] = useState(false)
  const attempt = useRef<{ key: string; amount: string }>(null)
  useEffect(() => { void api<Client[]>('/clients').then(setClients).catch(failure => setError(failure.message)) }, [])

  async function read(input: { id: string; as_of?: string }) {
    return api<Account>('/clients/' + input.id + '/account', 'POST', { as_of: input.as_of })
  }
  async function consult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const input = { id: String(form.get('client')), as_of: String(form.get('as_of') ?? '') || undefined }
    setError('')
    setResult(undefined)
    setBusy(true)
    try {
      setAccount(await read(input))
      setSelection(input)
      attempt.current = null
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }
  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selection || !account) return
    const amount = String(new FormData(event.currentTarget).get('amount'))
    if (attempt.current?.amount !== amount) attempt.current = { amount, key: crypto.randomUUID() }
    setBusy(true)
    setError('')
    try {
      const receipt = await api<Receipt>('/clients/' + selection.id + '/payments', 'POST', {
        amount, as_of: selection.as_of, expected: account.liquidation.expected,
        idempotency_key: attempt.current.key,
      })
      setResult(receipt)
      setAccount(await read(selection))
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <h1>{isPayment ? 'Pagos' : 'Cuentas por cobrar'}</h1>
    {error && <p className="error" role="alert">{error}</p>}
    <form className="panel stack" onSubmit={consult}>
      <div className="fields">
        <label>Cliente<select name="client" required aria-label="Cliente"><option value="">Selecciona un cliente</option>
          {clients.map(client => <option key={client.id} value={client.id}>{client.name}{!client.active ? ' (inactivo)' : ''}</option>)}
        </select></label>
        {demo && <label>Fecha y hora de consulta para demo<input name="as_of" placeholder="2026-09-29T12:00:00-05:00" />
          <small>Formato ISO con desplazamiento horario.</small></label>}
      </div>
      <div><button disabled={busy}>Consultar cuenta</button></div>
    </form>
    {result && <p role="status" className="panel">Cobro #{result.id} registrado por {money(result.currency, result.amount)}.</p>}
    {account && <>
      <Summary account={account} />
      <Liquidation account={account} />
      {isPayment && account.liquidation.rows.length > 0 && <form key={selection?.id + account.liquidation.amount} className="panel stack" onSubmit={register}>
        <label>Importe recibido<input name="amount" type="number" step="0.01" min="0.01" defaultValue={account.liquidation.amount} required />
          <small>Debe coincidir con el exigible íntegro. Se aplica a mora, interés compensatorio y capital.</small></label>
        <div><button disabled={busy}>Registrar cobro</button></div>
      </form>}
      {isPayment ? <Payments account={account} /> : <Statements account={account} />}
    </>}
  </>
}

export function CustomerAccount() {
  const [account, setAccount] = useState<Account>()
  const [error, setError] = useState('')
  useEffect(() => { void api<Account>('/my-account').then(setAccount).catch(failure => setError(failure.message)) }, [])
  return <>
    {error && <p className="error" role="alert">{error}</p>}
    {account && <><Summary account={account} /><Liquidation account={account} /><Statements account={account} /><Payments account={account} /></>}
  </>
}
