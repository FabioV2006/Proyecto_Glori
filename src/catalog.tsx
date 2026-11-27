import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, formValues } from './api'

type Rate = { kind: 'effective' | 'nominal'; value: string; period_days?: number; capitalization_days?: number }
export type Product = {
  id: number; name: string; active: boolean; kind: string; description: string; brand: string
  unit: string; supplier: string; image: string; cash_price: string; credit_price: string; currency: string
  single_allowed: boolean; monthly_allowed: boolean
}
export type Client = {
  id: number; name: string; active: boolean; document: string; email: string; phone: string
  currency: string; credit_limit: string; max_months: number; cutoff_day: number; cutoff_time: string
  payment_day: number; compensatory: Rate; moratory: Rate; username: string
}

function Field({ title, name, value, type = 'text', hint, optional = false, min, max, step }: {
  title: string; name: string; value?: string | number; type?: string; hint?: string
  optional?: boolean; min?: number; max?: number; step?: string
}) {
  return <label>{title}<input name={name} defaultValue={value} type={type} required={!optional}
    min={min} max={max} step={step} />{hint && <small>{hint}</small>}</label>
}

function RateFields({ title, name, rate }: { title: string; name: string; rate?: Rate }) {
  const [kind, setKind] = useState<Rate['kind']>(rate?.kind ?? 'effective')
  return <fieldset><legend>{title}</legend><div className="fields">
    <label>Tipo<select name={name + '_kind'} value={kind} onChange={e => setKind(e.target.value as Rate['kind'])}>
      <option value="effective">Efectiva</option><option value="nominal">Nominal anual</option>
    </select></label>
    <Field title="Tasa en fracción decimal" name={name + '_value'} value={rate?.value ?? '0'}
      hint="Por ejemplo, 24 % se ingresa como 0.24." />
    {kind === 'effective'
      ? <Field key="period" title="Período efectivo en días" name={name + '_days'} type="number" value={rate?.period_days ?? 360} min={1} max={360} />
      : <Field key="cap" title="Capitalización en días" name={name + '_days'} type="number" value={rate?.capitalization_days ?? 30} min={1} max={360} />}
  </div></fieldset>
}

async function encodeImage(file: File) {
  if (file.size > 2_000_000) throw new Error('La imagen debe pesar como máximo 2 MB.')
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('No se pudo leer la imagen.'))
    reader.readAsDataURL(file)
  })
}

export function Catalog({ mode }: { mode: 'products' | 'clients' }) {
  const [rows, setRows] = useState<(Product | Client)[]>([])
  const [editing, setEditing] = useState<Product | Client | 'new' | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const products = mode === 'products'
  const title = products ? 'Catálogo' : 'Clientes'
  const entity = products ? 'ítem' : 'cliente'
  const refresh = async () => setRows(await api<(Client | Product)[]>('/' + mode))
  useEffect(() => { void refresh().catch(failure => setError(failure.message)) }, [mode])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = formValues(event.currentTarget)
    const current = typeof editing === 'object' ? editing : null
    setError('')
    setBusy(true)
    try {
      const payload: Record<string, unknown> = { ...values }
      if (products) {
        const file = values.image
        payload.image = file instanceof File && file.size ? await encodeImage(file) : (current as Product)?.image
        payload.single_allowed = values.single_allowed === 'on'
        payload.monthly_allowed = values.monthly_allowed === 'on'
      } else {
        for (const key of ['max_months', 'cutoff_day', 'payment_day']) payload[key] = Number(values[key])
        for (const key of ['compensatory', 'moratory']) {
          const kind = values[key + '_kind']
          payload[key] = {
            kind, value: values[key + '_value'],
            [kind === 'effective' ? 'period_days' : 'capitalization_days']: Number(values[key + '_days']),
          }
        }
      }
      await api('/' + mode + (current ? '/' + current.id : ''), current ? 'PUT' : 'POST', payload)
      setEditing(null)
      await refresh()
    } catch (failure) {
      setError((failure as Error).message)
    } finally { setBusy(false) }
  }

  async function toggle(row: Product | Client) {
    setError('')
    setBusy(true)
    try {
      await api('/' + mode + '/' + row.id, 'PATCH', { active: !row.active })
      await refresh()
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }

  const product = editing && editing !== 'new' && products ? editing as Product : undefined
  const client = editing && editing !== 'new' && !products ? editing as Client : undefined
  return <>
    <div className="page-head"><h1>{title}</h1><button onClick={() => { setError(''); setEditing('new') }}>
      {products ? 'Nuevo ítem' : 'Nuevo cliente'}</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {editing && <form key={editing === 'new' ? 'new' : editing.id} className="panel stack" onSubmit={save}>
      <h2>{editing === 'new' ? 'Alta de ' : 'Editar '}{entity}</h2>
      <div className="fields">
        <Field title="Nombre" name="name" value={product?.name ?? client?.name} />
        {products ? <>
          <label>Tipo<select name="kind" defaultValue={product?.kind ?? 'producto'}><option>producto</option><option>servicio</option></select></label>
          <Field title="Descripción" name="description" value={product?.description} />
          <Field title="Marca" name="brand" value={product?.brand} />
          <Field title="Unidad" name="unit" value={product?.unit} />
          <Field title="Proveedor" name="supplier" value={product?.supplier} optional />
          <label>Imagen<input type="file" name="image" accept="image/png,image/jpeg,image/webp" required={!product} /><small>PNG, JPEG o WebP de hasta 2 MB.</small></label>
          <Field title="Moneda de los precios" name="currency" value={product?.currency ?? 'PEN'} hint="Debe coincidir con la moneda del crédito." />
          <Field title="Precio contado" name="cash_price" value={product?.cash_price} type="number" min={0} step="0.01" />
          <Field title="Precio crédito" name="credit_price" value={product?.credit_price} type="number" min={.01} step="0.01" />
          <label className="check"><input type="checkbox" name="single_allowed" defaultChecked={product?.single_allowed ?? true} />Pago único</label>
          <label className="check"><input type="checkbox" name="monthly_allowed" defaultChecked={product?.monthly_allowed ?? true} />Crédito en cuotas</label>
        </> : <>
          <Field title="Documento" name="document" value={client?.document} optional />
          <Field title="Teléfono" name="phone" type="tel" value={client?.phone} optional />
          <Field title="Correo electrónico" name="email" type="email" value={client?.email} optional />
          {editing === 'new' && <>
            <Field title="Usuario del cliente" name="username" />
            <label>Contraseña inicial<input type="password" name="password" minLength={8} required /></label>
          </>}
          <Field title="Moneda" name="currency" value={client?.currency ?? 'PEN'} hint="Código de tres letras." />
          <Field title="Límite de crédito" name="credit_limit" value={client?.credit_limit ?? '500'} type="number" min={0} step="0.01" hint="Importe en la moneda pactada." />
          <Field title="Plazo máximo en meses" name="max_months" value={client?.max_months ?? 6} type="number" min={1} max={120} hint="Número máximo de cuotas mensuales." />
          <Field title="Día de corte" name="cutoff_day" value={client?.cutoff_day ?? 20} type="number" min={1} max={31} hint="En meses cortos, se usa el último día." />
          <Field title="Hora local de corte" name="cutoff_time" value={client?.cutoff_time ?? '18:00'} type="time" step="1" hint="Una compra exactamente a esta hora entra en el ciclo." />
          <Field title="Día de pago" name="payment_day" value={client?.payment_day ?? 26} type="number" min={1} max={31} hint="El vencimiento debe quedar después del corte." />
        </>}
      </div>
      {!products && <>
        <RateFields title="Tasa compensatoria" name="compensatory" rate={client?.compensatory} />
        <RateFields title="Tasa moratoria" name="moratory" rate={client?.moratory} />
      </>}
      <div className="actions"><button disabled={busy}>Guardar {entity}</button>
        <button type="button" className="secondary" onClick={() => setEditing(null)}>Cancelar</button></div>
    </form>}
    <section className="panel table-wrap">
      {rows.length ? <table><thead><tr><th>Nombre</th><th>{products ? 'Precio crédito' : 'Límite'}</th><th>Estado</th><th>Acciones</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.id}><td>{'image' in row && <img className="thumbnail" src={row.image} alt="" />}{row.name}</td>
          <td>{row.currency + ' ' + ('credit_price' in row ? row.credit_price : row.credit_limit)}</td>
          <td><span className={row.active ? 'status active' : 'status'}>{row.active ? 'Activo' : 'Inactivo'}</span></td>
          <td><div className="actions"><button className="secondary" onClick={() => setEditing(row)}>Editar</button>
            <button className="secondary" disabled={busy} onClick={() => void toggle(row)}>{row.active ? 'Desactivar' : 'Reactivar'}</button></div></td>
        </tr>)}</tbody></table> : <p>{products ? 'Aún no hay ítems registrados.' : 'Aún no hay clientes registrados.'}</p>}
    </section>
  </>
}

export function MyProfile() {
  const [client, setClient] = useState<Client | null>()
  const [error, setError] = useState('')
  useEffect(() => { void api<Client | null>('/my-profile').then(setClient).catch(failure => setError(failure.message)) }, [])
  return <><h1>Mi cuenta</h1>{error && <p role="alert" className="error">{error}</p>}
    {client && <section className="panel stack"><h2>{client.name}</h2>
      <p>Límite pactado · {client.currency} {client.credit_limit}</p>
      <p>Corte · día {client.cutoff_day} a las {client.cutoff_time.slice(0, 5)}</p>
      <p>Pago pactado · día {client.payment_day}</p>
    </section>}</>
}
