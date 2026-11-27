import { useEffect, useState } from 'react'
import { api } from './api'
import { modeName } from './accounts'

type Report = {
  clients: number; products: number
  currencies: { currency: string; original: string; pending: string; recovered: string; interest: string; mora: string; received: string; sales: number; payments: number }[]
  latest: { id: number; name: string; mode: string; currency: string; capital: string; sold_at: string }[]
}

export function Overview({ reports, navigate, timezone }: {
  reports: boolean; navigate: (section: string) => void; timezone?: string
}) {
  const [data, setData] = useState<Report>()
  const [error, setError] = useState('')
  useEffect(() => { void api<Report>('/reports').then(setData).catch(failure => setError(failure.message)) }, [])
  return <>
    <div className="page-head"><h1>{reports ? 'Reportes' : 'Inicio'}</h1>
      {!reports && <button onClick={() => navigate('Nueva venta')}>Registrar venta</button>}
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {data && <>
      {!reports && <div className="fields">
        <div className="panel metric"><p>Clientes activos</p><strong>{data.clients}</strong></div>
        <div className="panel metric"><p>Ítems activos</p><strong>{data.products}</strong></div>
        {data.currencies.map(row => <div className="panel metric" key={row.currency}>
          <p>Capital pendiente</p><strong>{row.currency} {row.pending}</strong>
        </div>)}
      </div>}
      <section className="panel table-wrap stack">
        <h2>{reports ? 'Ventas y cobranzas por moneda' : 'Ventas recientes'}</h2>
        {reports ? data.currencies.length ? <table>
          <thead><tr><th>Moneda</th><th>Ventas</th><th>Capital vendido</th><th>Capital pendiente</th><th>Capital cobrado</th><th>Compensatorio</th><th>Mora</th><th>Total cobrado</th></tr></thead>
          <tbody>{data.currencies.map(row => <tr key={row.currency}><td>{row.currency}</td><td>{row.sales}</td>
            <td>{row.original}</td><td>{row.pending}</td><td>{row.recovered}</td><td>{row.interest}</td><td>{row.mora}</td><td>{row.received}</td></tr>)}</tbody>
        </table> : <p>Aún no hay operaciones para emitir un reporte.</p> : data.latest.length ? <table>
          <thead><tr><th>Venta</th><th>Cliente</th><th>Fecha</th><th>Modalidad</th><th>Capital</th></tr></thead>
          <tbody>{data.latest.map(row => <tr key={row.id}><td>#{row.id}</td><td>{row.name}</td>
            <td>{new Intl.DateTimeFormat('es-PE', { dateStyle: 'short', timeZone: timezone }).format(new Date(row.sold_at))}</td>
            <td>{modeName(row.mode)}</td><td>{row.currency} {row.capital}</td></tr>)}</tbody>
        </table> : <p>Aún no hay ventas registradas.</p>}
      </section>
    </>}
  </>
}

export function Settings() {
  const [shop, setShop] = useState<{ name: string; timezone: string; active: boolean }>()
  const [error, setError] = useState('')
  useEffect(() => { void api<typeof shop>('/shop').then(setShop).catch(failure => setError(failure.message)) }, [])
  return <><h1>Configuración</h1>{error && <p className="error" role="alert">{error}</p>}
    {shop && <section className="panel stack"><h2>{shop.name}</h2>
      <p>Zona horaria del comercio · {shop.timezone}</p>
      <p>Estado · {shop.active ? 'Activo' : 'Inactivo'}</p>
      <p>Las fechas de corte, los límites y las tasas se pactan en la ficha de cada cliente.</p>
    </section>}</>
}
