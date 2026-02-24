import pandas as pd

df = pd.read_csv(r'outputs/control_gastos.csv')
df['Fecha'] = pd.to_datetime(df['Fecha'], format='mixed', dayfirst=True)
cost_col = 'Coste Total (USD)' if 'Coste Total (USD)' in df.columns else 'Coste Estimado (USD)'

print("=== TOTAL ACUMULADO ===")
print(f"  Registros: {len(df):,}")
print(f"  Tokens totales: {df['Total Tokens'].sum():,.0f}")
total_usd = df[cost_col].sum()
print(f"  Coste total: ${total_usd:.4f} USD  (~EUR {total_usd*0.92:.4f})")

print()
print("=== POR FECHA (ultimas 10) ===")
by_date = df.groupby('Fecha').agg(
    calls=(cost_col, 'count'),
    tokens=('Total Tokens', 'sum'),
    coste=(cost_col, 'sum')
).tail(10)
for idx, row in by_date.iterrows():
    eur = row['coste'] * 0.92
    print(f"  {idx.strftime('%d/%m/%Y')}: {int(row['calls']):3} operaciones | {int(row['tokens']):>8,} tokens | ${row['coste']:.4f} USD (~EUR {eur:.4f})")

print()
print("=== TOP 10 TIPOS MAS COSTOSOS ===")
by_ref = df.groupby('Archivo/Referencia')[cost_col].agg(['sum','count']).sort_values('sum', ascending=False).head(10)
for ref, row in by_ref.iterrows():
    print(f"  ${row['sum']:.4f} ({int(row['count']):4} ops) - {ref[:60]}")

print()
print("=== HOY ===")
hoy = df[df['Fecha'] == df['Fecha'].max()]
print(f"  Operaciones: {len(hoy)}")
print(f"  Tokens: {hoy['Total Tokens'].sum():,}")
coste_hoy = hoy[cost_col].sum()
print(f"  Coste: ${coste_hoy:.4f} USD (~EUR {coste_hoy*0.92:.4f})")
