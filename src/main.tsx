import { createRoot } from 'react-dom/client'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, formValues } from './api'
import { Catalog, MyProfile } from './catalog'
import { NewSale, Schedules } from './sales'
import { CustomerAccount, ShopAccount } from './accounts'
import { Overview, Settings } from './overview'
import { Simulator } from './simulator'
import { Calculator } from 'lucide-react'
import { ArrowRight, BookOpen, CalendarDays, ChartColumn, ContactRound, House, LogOut, Menu, Package, ReceiptText, Settings2, Store, Wallet, X } from 'lucide-react'
import '@fontsource-variable/dm-sans'
import '@fontsource/fraunces/latin-600.css'
import './style.css'

type User = {
  id: number
  role: 'platform' | 'shop' | 'client'
  username: string
  shop_name: string | null
  demo_dates?: boolean
  timezone?: string
}

type Shop = { id: number; name: string; timezone: string; active: boolean; showcase: boolean }
const roles = { platform: 'Administrador de plataforma', shop: 'Administrador de tienda', client: 'Cliente' }
const sections = [
  ['Inicio', House], ['Catálogo', Package], ['Clientes', ContactRound], ['Nueva venta', ReceiptText],
  ['Cuentas por cobrar', BookOpen], ['Cronogramas', CalendarDays], ['Pagos', Wallet],
  ['Simulador', Calculator], ['Reportes', ChartColumn], ['Configuración', Settings2],
] as const

function ErrorMessage({ message }: { message: string }) {
  return message ? <p role="alert" className="error">{message}</p> : null
}

function Brand() {
  return <div className="brand"><Store aria-hidden="true" /><div><strong>Glori</strong><small>Créditos y cobranzas</small></div></div>
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [demo, setDemo] = useState(false)
  useEffect(() => {
    void api<{ demo: boolean }>('/login-options').then(result => setDemo(result.demo)).catch(() => {})
  }, [])
  async function signIn(values: unknown) {
    setBusy(true)
    setError('')
    try {
      await api('/login', 'POST', values)
      onLogin(await api<User>('/me'))
    } catch (failure) {
      setError(String((failure as Error).message))
    } finally {
      setBusy(false)
    }
  }
  return <main className="login">
    <section className="login-intro"><Brand /><div className="login-caption"><h1>Crédito para tu comercio.</h1>
      <p>Consulta tu cuenta o administra las ventas y cobranzas de tu tienda.</p></div>
    </section>
    <section className="login-form"><div className="login-options"><form onSubmit={event => {
      event.preventDefault()
      void signIn(formValues(event.currentTarget))
    }} className="panel stack">
      <h2>Iniciar sesión</h2>
      <label>Usuario<input name="username" autoComplete="username" required /></label>
      <label>Contraseña<input name="password" type="password" autoComplete="current-password" required /></label>
      <ErrorMessage message={error} />
      <button disabled={busy}>{busy ? 'Ingresando…' : 'Ingresar'} <ArrowRight size={18} aria-hidden="true" /></button>
    </form>
    {demo && <section className="panel stack" aria-label="Accesos de demostración">
      <h2>Probar la demo</h2>
      <button disabled={busy} onClick={() => void signIn({ username: 'gloria.admin', password: 'Glori-demo-2026' })}>
        Entrar a Bodegas Gloria
      </button>
      <small>Abre el panel con ventas, clientes, cuentas por cobrar, pagos y reportes.</small>
      <div className="actions">
        <button className="secondary" disabled={busy} onClick={() => void signIn({ username: 'gloria.cliente', password: 'Glori-demo-2026' })}>Ver mi cuenta</button>
        <button className="secondary" disabled={busy} onClick={() => void signIn({ username: 'demo.plataforma', password: 'Glori-demo-2026' })}>Gestionar tiendas</button>
      </div>
    </section>}</div></section>
  </main>
}

function Shops({ switchAccount, onEnter }: { switchAccount: () => void; onEnter: (user: User) => void }) {
  const [shops, setShops] = useState<Shop[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  async function refresh() {
    setShops(await api<Shop[]>('/shops'))
  }
  async function enterShowcase(role: 'shop' | 'client') {
    setBusy(true)
    setError('')
    try {
      await api('/showcase/access', 'POST', {role})
      onEnter(await api<User>('/me'))
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => {
    void refresh().catch(failure => setError(failure.message)).finally(() => setLoading(false))
  }, [])
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api('/shops', 'POST', formValues(event.currentTarget))
      setCreating(false)
      await refresh()
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function toggle(shop: Shop) {
    setError('')
    setBusy(true)
    try {
      await api('/shops/' + shop.id, 'PATCH', { active: !shop.active })
      await refresh()
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return <>
    <div className="page-head"><div><h1>Tiendas</h1><p>Administra los comercios de la plataforma.</p></div>
      {!creating && <button onClick={() => setCreating(true)}>Nueva tienda</button>}
    </div>
    {shops.some(shop => shop.showcase && shop.active) && <section className="panel stack">
      <h2>Bodega Santa Rosa · Demostración</h2>
      <p>Consulta el cronograma de Ana Torres, la deuda vencida de Luis Medina y el cobro de Rosa Campos.</p>
      <div className="actions"><button disabled={busy} onClick={() => void enterShowcase('shop')}>Entrar a la tienda demo</button>
        <button className="secondary" disabled={busy} onClick={() => void enterShowcase('client')}>Ver como Ana Torres</button></div>
    </section>}
    <section className="panel account-guide">
      <div><h2>Operar una tienda</h2>
        <p>Ingresa con el usuario de un comercio para registrar ventas, consultar cuentas y cobrar.</p>
      </div>
      <button className="secondary" onClick={switchAccount}>Cambiar de cuenta</button>
    </section>
    <ErrorMessage message={error} />
    {creating && <form className="panel stack" onSubmit={create}>
      <h2>Nueva tienda</h2>
      <div className="fields">
        <label>Nombre de la tienda<input name="name" required /></label>
        <label>Zona horaria<input name="timezone" defaultValue="America/Lima" required />
          <small>Identificador IANA para interpretar el corte local.</small></label>
        <label>Usuario del administrador<input name="username" autoComplete="off" required /></label>
        <label>Contraseña inicial<input name="password" type="password" minLength={8} required /></label>
      </div>
      <div className="actions"><button disabled={busy}>Guardar tienda</button>
        <button type="button" className="secondary" onClick={() => setCreating(false)}>Cancelar</button></div>
    </form>}
    <section className="panel table-wrap">
      {loading ? <p>Cargando tiendas…</p> : shops.length === 0 ? <p>Aún no hay tiendas registradas.</p> :
        <table><thead><tr><th>Tienda</th><th>Zona horaria</th><th>Estado</th><th>Acción</th></tr></thead>
          <tbody>{shops.map(shop => <tr key={shop.id}><td>{shop.name}</td><td>{shop.timezone}</td>
            <td><span className={shop.active ? 'status active' : 'status'}>{shop.active ? 'Activa' : 'Inactiva'}</span></td>
            <td><button className="secondary" disabled={busy} onClick={() => void toggle(shop)}>
              {shop.active ? 'Desactivar' : 'Reactivar'}</button></td>
          </tr>)}</tbody>
        </table>}
    </section>
  </>
}

function App() {
  const [user, setUser] = useState<User | null>()
  const [error, setError] = useState('')
  const [shopSection, setShopSection] = useState('Inicio')
  const [menuOpen, setMenuOpen] = useState(false)
  useEffect(() => {
    void api<User | null>('/me').then(setUser).catch(failure => setError(failure.message))
  }, [])
  async function logout() {
    try {
      await api('/logout', 'POST')
      setUser(null)
      setShopSection('Inicio')
      setMenuOpen(false)
    } catch (failure) {
      setError((failure as Error).message)
    }
  }
  if (user === undefined) return <main className="panel"><ErrorMessage message={error} />{!error && 'Cargando Glori…'}</main>
  if (!user) return <Login onLogin={setUser} />
  const section = user.role === 'platform' ? 'Tiendas' : user.role === 'shop' ? shopSection : 'Mi cuenta'
  return <div className="shell">
    <aside><div className="rail-head"><Brand />
      {user.role === 'shop' && <button className="menu-toggle" aria-controls="sections" aria-expanded={menuOpen}
        onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />} Menú</button>}</div>
      {user.shop_name && <div className="shop-context"><strong>{user.shop_name}</strong><small>{roles[user.role]}</small></div>}
      <nav id="sections" className={menuOpen ? 'open' : ''} aria-label="Navegación principal">
      {user.role === 'shop' ? sections.map(([label, Icon]) =>
        <button key={label} aria-current={label === section ? 'page' : undefined}
          onClick={() => { setShopSection(label); setMenuOpen(false) }}><Icon size={18} aria-hidden="true" />{label === 'Nueva venta' ? 'Ventas al crédito' : label}</button>) : <span aria-current="page">{section}</span>}
    </nav></aside>
    <div className="workspace">
      <header><div><strong>{user.shop_name ?? 'Plataforma Glori'}</strong><small>{roles[user.role]} · {user.username}</small></div>
        <button className="secondary" onClick={() => void logout()}><LogOut size={16} aria-hidden="true" />Cerrar sesión</button>
      </header>
      <main key={section}><ErrorMessage message={error} />
        {user.role === 'platform' ? <Shops switchAccount={() => void logout()} onEnter={setUser} /> : user.role === 'client' ? <><MyProfile /><CustomerAccount /></> :
          section === 'Catálogo' ? <Catalog key="products" mode="products" /> :
          section === 'Clientes' ? <Catalog key="clients" mode="clients" /> :
          section === 'Nueva venta' ? <NewSale demo={!!user.demo_dates} /> :
          section === 'Cronogramas' ? <Schedules /> :
          section === 'Simulador' ? <Simulator /> :
          section === 'Cuentas por cobrar' ? <ShopAccount key="account" demo={!!user.demo_dates} isPayment={false} /> :
          section === 'Pagos' ? <ShopAccount key="payments" demo={!!user.demo_dates} isPayment /> :
          section === 'Configuración' ? <Settings /> :
          <Overview reports={section === 'Reportes'} navigate={setShopSection} timezone={user.timezone} />}
      </main>
    </div>
  </div>
}

createRoot(document.getElementById('root')!).render(<App />)
