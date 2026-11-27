import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

test('el simulador recalcula plazo, gracia y mora y bloquea entradas inválidas', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Entrar a Bodegas Gloria' }).click()
  await page.getByRole('button', { name: 'Simulador' }).click()
  await page.getByLabel('Plazo en meses').fill('2')
  const table = page.getByRole('table')
  const rows = table.locator('tbody tr')
  await expect(rows).toHaveCount(4)
  await page.getByLabel('Gracia del periodo 1').selectOption('total')
  await page.getByLabel('Gracia del periodo 2').selectOption('partial')
  await page.getByLabel('Días de demora del periodo 3').fill('5')
  await expect(rows.nth(2)).toContainText('515.10')
  await expect(page.getByRole('heading', { name: 'Resumen del préstamo' })).toBeVisible()
  await page.getByLabel('TEA (%)', {exact: true}).fill('0')
  await expect(page.getByRole('alert')).toContainText('mayor que cero')
  await expect(table.getByText('515.10')).toHaveCount(0)
  await page.getByLabel('TEA (%)', {exact: true}).fill('25')
  await page.getByLabel('Días de demora del periodo 3').fill('-1')
  await expect(page.getByRole('alert')).toContainText('enteros')
  await page.getByRole('button', { name: 'Cargar ejemplo de bodega' }).click()
  await expect(rows.nth(0)).toContainText('350.00')
  await expect(rows.nth(3)).toContainText('Nueva tasa')
  await expect(rows.nth(5).getByRole('cell').nth(7)).toHaveText('0.00')
  const details = page.getByLabel('Datos del cronograma')
  await expect(details).toContainText('S/ 50.00 (12.5 %)')
  await expect(details).toContainText('Cada 15 días')
  await page.getByRole('button', { name: 'Gracia parcial y atraso' }).click()
  await expect(details).toContainText('S/ 150.00 (30 %)')
  await expect(page.getByLabel('Días de demora del periodo 2')).toHaveValue('5')
  await expect(rows).toHaveCount(4)
  await page.getByRole('button', { name: 'Pago puntual' }).click()
  await expect(details).toContainText('1 mes')
  await expect(rows).toHaveCount(2)
})

test('el acceso y el menú del comercio funcionan a 360 px con movimiento reducido', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible()
  await page.getByRole('button', { name: 'Entrar a Bodegas Gloria' }).click()
  const menu = page.getByRole('button', { name: 'Menú' })
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  await menu.click()
  await page.getByRole('button', { name: 'Ventas al crédito' }).click()
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('button', { name: 'Previsualizar' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
})

async function login(page: Page, username: string, password = 'Glori-demo-2026') {
  await page.getByLabel('Usuario', { exact: true }).fill(username)
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Ingresar' }).click()
}

test('acceso de demostración al menú del comercio desde el perfil de plataforma', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Gestionar tiendas' }).click()
  await expect(page.getByRole('heading', { name: 'Tiendas' })).toBeVisible()
  await page.getByRole('button', { name: 'Cambiar de cuenta' }).click()
  await page.getByRole('button', { name: 'Entrar a Bodegas Gloria' }).click()
  const menu = page.getByRole('navigation', { name: 'Navegación principal' })
  for (const section of ['Catálogo', 'Clientes', 'Ventas al crédito', 'Cuentas por cobrar', 'Cronogramas', 'Pagos', 'Reportes', 'Configuración']) {
    await expect(menu.getByRole('button', { name: section, exact: true })).toBeVisible()
  }
  await expect(page.getByRole('heading', { name: 'Ventas recientes' })).toBeVisible()
})

test('alta y baja de tienda desde la pantalla de plataforma', async ({ page }) => {
  await page.goto('/')
  await login(page, 'demo.plataforma')
  await expect(page.getByRole('heading', { name: 'Tiendas' })).toBeVisible()
  const id = Date.now().toString(36)
  const name = 'Tienda e2e ' + id
  const username = 'e2e.' + id
  await page.getByRole('button', { name: 'Nueva tienda' }).click()
  await page.getByLabel('Nombre de la tienda').fill(name)
  await page.getByLabel('Usuario del administrador').fill(username)
  await page.getByLabel('Contraseña inicial').fill('Glori-e2e-2026')
  await page.getByRole('button', { name: 'Guardar tienda' }).click()
  const row = page.getByRole('row').filter({ hasText: name })
  await expect(row.getByText('Activa', { exact: true })).toBeVisible()
  await row.getByRole('button', { name: 'Desactivar' }).click()
  await expect(row.getByText('Inactiva', { exact: true })).toBeVisible()
  await page.reload()
  await expect(row.getByText('Inactiva', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await login(page, username, 'Glori-e2e-2026')
  await expect(page.getByRole('alert')).toHaveText('Usuario o contraseña incorrectos.')
})

test('tienda y cliente aterrizan en sus áreas al iniciar sesión', async ({ page }) => {
  await page.goto('/')
  await login(page, 'gloria.admin')
  await expect(page.getByRole('heading', { name: 'Inicio' })).toBeVisible()
  await expect(page.getByRole('banner')).toContainText('Bodegas Gloria')
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await login(page, 'panaderia.cliente')
  await expect(page.getByRole('heading', { name: 'Mi cuenta' })).toBeVisible()
  await expect(page.getByRole('banner')).toContainText('Panadería del Barrio')
})

test('un comercio registra un producto con imagen y lo desactiva', async ({ page }) => {
  await page.goto('/')
  await login(page, 'gloria.admin')
  await page.getByRole('button', { name: 'Catálogo' }).click()
  await page.getByRole('button', { name: 'Nuevo ítem' }).click()
  const name = 'Arroz ' + Date.now()
  await page.getByLabel('Nombre', { exact: true }).fill(name)
  await page.getByLabel('Descripción').fill('Arroz por kilo')
  await page.getByLabel('Marca').fill('Demo')
  await page.getByLabel('Unidad').fill('kg')
  await page.getByLabel('Precio contado').fill('5')
  await page.getByLabel('Precio crédito').fill('6')
  await page.getByLabel('Imagen').setInputFiles({
    name: 'arroz.png', mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l2kAAAAASUVORK5CYII=', 'base64'),
  })
  await page.getByRole('button', { name: 'Guardar ítem' }).click()
  const row = page.getByRole('row').filter({ hasText: name })
  await expect(row.getByText('Activo', { exact: true })).toBeVisible()
  await row.getByRole('button', { name: 'Desactivar' }).click()
  await expect(row.getByText('Inactivo', { exact: true })).toBeVisible()
})

async function commerceFixture(page: Page) {
  const suffix = Date.now().toString(36)
  const product = await page.request.post('/api/products', { data: {
    name: 'Producto ' + suffix, kind: 'producto', description: 'Producto de prueba', brand: 'Demo',
    unit: 'unidad', image: 'data:image/png;base64,AAAA', cash_price: '90.00',
    credit_price: '100.00', single_allowed: true, monthly_allowed: true,
  } })
  const rate = { kind: 'effective', value: '0.24', period_days: 360 }
  const client = await page.request.post('/api/clients', { data: {
    name: 'Cliente ' + suffix, username: 'cliente.' + suffix, password: 'Glori-e2e-2026',
    currency: 'PEN', credit_limit: '500.00', max_months: 6, cutoff_day: 20,
    cutoff_time: '18:00', payment_day: 26, compensatory: rate,
    moratory: { ...rate, value: '0.30' },
  } })
  expect(product.status()).toBe(201)
  expect(client.status()).toBe(201)
  return { product: await product.json(), client: await client.json() }
}

test('el comercio confirma desde pantalla las tres cuotas del ejemplo SI642', async ({ page }) => {
  await page.goto('/')
  await login(page, 'gloria.admin')
  await expect(page.getByRole('heading', { name: 'Inicio' })).toBeVisible()
  const { product, client } = await commerceFixture(page)
  await page.getByRole('button', { name: 'Ventas al crédito' }).click()
  await page.locator('select[name=client_id]').selectOption(String(client.id))
  await page.getByLabel('Modalidad').selectOption('monthly')
  await page.locator('select[name=product_0]').selectOption(String(product.id))
  await page.getByLabel('Fecha y hora de compra para demo').fill('2026-09-15T12:00:00-05:00')
  await page.getByRole('button', { name: 'Previsualizar' }).click()
  await expect(page.getByText('Gracia inicial · 11 días')).toBeVisible()
  for (const date of ['2026-10-26', '2026-11-26', '2026-12-26']) {
    await expect(page.getByRole('cell', { name: date })).toBeVisible()
  }
  await page.getByRole('button', { name: 'Confirmar venta' }).click()
  await expect(page.getByRole('heading', { name: /Venta registrada/ })).toBeVisible()
  await page.getByRole('button', { name: 'Cronogramas' }).click()
  await page.locator('select[name=client]').selectOption(String(client.id))
  await page.getByRole('button', { name: 'Consultar cronogramas' }).click()
  await expect(page.getByRole('cell', { name: '2026-12-26' })).toBeVisible()
  await expect(page.getByLabel('Datos del cronograma')).toContainText('Mensual')
  await expect(page.getByRole('columnheader', { name: 'TEM (30 días)' })).toBeVisible()
  await page.getByRole('button', { name: 'Ver ejemplos quincenales' }).click()
  await expect(page.getByRole('button', { name: 'Cargar ejemplo de bodega' })).toBeVisible()
})

test('corte inclusivo y cobro íntegro desde Cuentas por cobrar y Pagos', async ({ page }) => {
  await page.goto('/')
  await login(page, 'gloria.admin')
  await expect(page.getByRole('heading', { name: 'Inicio' })).toBeVisible()
  const { product, client } = await commerceFixture(page)
  for (const sold_at of ['2026-09-15T12:00:00-05:00', '2026-09-20T18:00:00-05:00', '2026-09-21T12:00:00-05:00']) {
    const payload = { client_id: client.id, mode: 'single', sold_at,
      lines: [{ product_id: product.id, quantity: 1 }] }
    const quote = await page.request.post('/api/sales/preview', { data: payload })
    expect(quote.status()).toBe(200)
    const sale = await page.request.post('/api/sales', { data: { ...payload, expected: (await quote.json()).expected } })
    expect(sale.status()).toBe(201)
  }
  const consult = async (screen: string) => {
    await page.getByRole('button', { name: screen, exact: true }).click()
    await page.locator('select[name=client]').selectOption(String(client.id))
    await page.getByLabel('Fecha y hora de consulta para demo').fill('2026-09-27T12:00:00-05:00')
    await page.getByRole('button', { name: 'Consultar cuenta' }).click()
  }
  await consult('Cuentas por cobrar')
  await page.locator('summary').click()
  const statement = page.locator('details[open]')
  await expect(statement.getByRole('row')).toHaveCount(3)
  await expect(statement).toContainText('Capital PEN 200.00')
  await consult('Pagos')
  await expect(page.getByText('Total 201.17', { exact: true })).toBeVisible()
  await page.getByLabel('Importe recibido').fill('100.00')
  await page.getByRole('button', { name: 'Registrar cobro' }).click()
  await expect(page.getByRole('alert')).toContainText('importe exigible íntegro')
  await page.getByLabel('Importe recibido').fill('201.17')
  await page.getByRole('button', { name: 'Registrar cobro' }).click()
  await expect(page.getByRole('status')).toContainText('201.17')
  await expect(page.getByText('Crédito disponible · PEN 400.00')).toBeVisible()
  await expect(page.getByRole('cell', { name: '0.15' })).toBeVisible()
  await page.getByRole('button', { name: 'Reportes', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Ventas y cobranzas por moneda' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'PEN', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Configuración', exact: true }).click()
  await expect(page.getByText('Zona horaria del comercio · America/Lima')).toBeVisible()
})
