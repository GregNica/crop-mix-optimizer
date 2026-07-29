from pathlib import Path
from openpyxl import Workbook

out_dir = Path('/home/gregnica/excel-app/validation/phase4_mc_pack')
out_dir.mkdir(parents=True, exist_ok=True)

def write_mc_workbook(path: Path, years, yield_rows, price_rows, demand_rows):
    wb = Workbook()
    ws_i = wb.active
    ws_i.title = 'Instructions'
    ws_i.append(['Phase 4 Validation Pack'])
    ws_i.append(['Use Yield/Price/Demand tabs only. Keep names exact and case-sensitive.'])
    ws_i.append(['Years can be edited or columns removed as needed.'])

    def add_tab(name, unit, rows):
        ws = wb.create_sheet(name)
        hdr = ['crop_name'] + (['channel_name'] if name in ('Price', 'Demand') else []) + [f'Year_{y}' for y in years] + ['avg', 'stddev']
        units = ['(text)'] + (['(text)'] if name in ('Price', 'Demand') else []) + [unit for _ in years] + ['(auto)', '(auto)']
        ws.append(hdr)
        ws.append(units)
        for r in rows:
            ws.append(r)

    add_tab('Yield', 'lbs/acre', yield_rows)
    add_tab('Price', '$/lb', price_rows)
    add_tab('Demand', 'lbs/wk', demand_rows)
    wb.save(path)


def write_rainfall_workbook(path: Path, years, per_year_series):
    wb = Workbook()
    ws_i = wb.active
    ws_i.title = 'Instructions'
    ws_i.append(['Rainfall Validation Workbook'])
    ws_i.append(['Data tab uses matrix format: week, Year_YYYY..., avg_rainfall, stddev_rainfall'])

    ws = wb.create_sheet('Data')
    hdr = ['week'] + [f'Year_{y}' for y in years] + ['avg_rainfall', 'stddev_rainfall']
    units = ['(1-52)'] + ['mm/week' for _ in years] + ['(auto)', '(auto)']
    ws.append(hdr)
    ws.append(units)
    for w in range(1, 53):
        vals = [per_year_series[y][w - 1] for y in years]
        avg = sum(vals) / len(vals)
        var = sum((v - avg) ** 2 for v in vals) / len(vals)
        ws.append([w, *vals, round(avg, 2), round(var ** 0.5, 2)])
    wb.save(path)


years = [2018, 2019, 2020, 2021, 2022, 2023, 2024]

# Pack A: Low-variance baseline (tight distribution)
yield_rows_low = [
    ['Spinach', 3200, 3250, 3180, 3220, 3210, 3240, 3230, 3219, 23],
    ['Garlic', 840, 845, 838, 842, 841, 844, 843, 842, 2],
    ['Cucumbers', 11800, 12000, 11950, 12050, 11920, 12010, 11980, 11973, 78],
]
price_rows_low = [
    ['Spinach', 'Wholesale', 1.78, 1.80, 1.79, 1.81, 1.80, 1.79, 1.80, 1.80, 0.01],
    ['Spinach', 'Farmers Market', 4.45, 4.50, 4.48, 4.52, 4.50, 4.49, 4.51, 4.49, 0.02],
    ['Garlic', 'Wholesale', 4.45, 4.50, 4.48, 4.52, 4.50, 4.49, 4.51, 4.49, 0.02],
    ['Garlic', 'Farmers Market', 6.90, 7.00, 6.95, 7.05, 7.00, 6.98, 7.02, 6.99, 0.05],
    ['Cucumbers', 'Wholesale', 0.54, 0.55, 0.56, 0.55, 0.55, 0.54, 0.55, 0.55, 0.01],
    ['Cucumbers', 'Farmers Market', 1.45, 1.50, 1.48, 1.52, 1.50, 1.49, 1.51, 1.49, 0.02],
]
demand_rows_low = [
    ['Spinach', 'Wholesale', 24500, 25000, 25200, 24800, 24900, 25100, 25050, 24936, 234],
    ['Spinach', 'Farmers Market', 5900, 6000, 6100, 5950, 6050, 6000, 6100, 6014, 69],
    ['Garlic', 'Wholesale', 4100, 4200, 4250, 4150, 4200, 4180, 4220, 4186, 47],
    ['Garlic', 'Farmers Market', 950, 1000, 1020, 980, 990, 1000, 1010, 993, 22],
    ['Cucumbers', 'Wholesale', 49500, 50000, 50500, 49800, 50200, 50000, 50600, 50086, 344],
    ['Cucumbers', 'Farmers Market', 5800, 6000, 6100, 5950, 6050, 6000, 6150, 6007, 111],
]
write_mc_workbook(out_dir / 'mc_uncertainty_low_variance.xlsx', years, yield_rows_low, price_rows_low, demand_rows_low)

# Pack B: Spinach/FM shock driver (larger variance, should appear as top sensitivity)
yield_rows_shock = [
    ['Spinach', 2800, 3600, 3000, 3550, 2950, 3650, 3050, 3229, 337],
    ['Garlic', 830, 850, 840, 845, 835, 848, 842, 841, 7],
    ['Cucumbers', 11200, 12600, 11500, 12400, 11600, 12550, 11700, 11936, 533],
]
price_rows_shock = [
    ['Spinach', 'Wholesale', 1.40, 2.20, 1.55, 2.05, 1.60, 2.15, 1.50, 1.78, 0.31],
    ['Spinach', 'Farmers Market', 3.00, 6.20, 3.40, 5.80, 3.20, 6.00, 3.30, 4.41, 1.34],
    ['Garlic', 'Wholesale', 4.20, 4.80, 4.30, 4.70, 4.35, 4.75, 4.40, 4.50, 0.22],
    ['Garlic', 'Farmers Market', 6.40, 7.60, 6.60, 7.40, 6.70, 7.50, 6.80, 7.00, 0.44],
    ['Cucumbers', 'Wholesale', 0.45, 0.68, 0.49, 0.65, 0.50, 0.66, 0.48, 0.56, 0.09],
    ['Cucumbers', 'Farmers Market', 1.10, 1.90, 1.20, 1.80, 1.25, 1.85, 1.18, 1.47, 0.33],
]
demand_rows_shock = [
    ['Spinach', 'Wholesale', 22000, 28500, 23000, 27800, 23500, 28200, 24000, 25286, 2610],
    ['Spinach', 'Farmers Market', 4200, 8200, 4500, 7900, 4700, 8100, 4600, 6031, 1525],
    ['Garlic', 'Wholesale', 3800, 4600, 3900, 4500, 3950, 4550, 4000, 4186, 298],
    ['Garlic', 'Farmers Market', 800, 1300, 850, 1250, 900, 1280, 880, 1037, 188],
    ['Cucumbers', 'Wholesale', 45000, 56000, 46000, 55000, 47000, 55500, 46500, 50143, 4306],
    ['Cucumbers', 'Farmers Market', 4500, 7600, 4700, 7400, 4800, 7500, 4650, 5879, 1264],
]
write_mc_workbook(out_dir / 'mc_uncertainty_spinach_fm_shock.xlsx', years, yield_rows_shock, price_rows_shock, demand_rows_shock)

# Rainfall packs
rain_years = list(range(2010, 2025))
stable = {}
volatile = {}
for y in rain_years:
    # stable profile: gentle seasonality, low variance
    stable[y] = [max(0, round(10 + 6 * __import__('math').sin((w / 52) * 6.28318) + (y % 3 - 1) * 0.8, 2)) for w in range(1, 53)]
    # volatile profile: amplified seasonality + year shocks
    year_shock = ((y % 5) - 2) * 3.5
    volatile[y] = [max(0, round(10 + 16 * __import__('math').sin((w / 52) * 6.28318) + year_shock + ((w % 7) - 3) * 0.9, 2)) for w in range(1, 53)]

write_rainfall_workbook(out_dir / 'rainfall_history_stable.xlsx', rain_years, stable)
write_rainfall_workbook(out_dir / 'rainfall_history_volatile.xlsx', rain_years, volatile)

print('Generated files:')
for p in sorted(out_dir.glob('*.xlsx')):
    print('-', p.name)
