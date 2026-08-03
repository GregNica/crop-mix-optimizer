"""adapter.py — the JSON-in/JSON-out entry point every caller converges on.

``run_from_js(params_json)`` takes the browser's (or a server caller's) payload, normalises it,
hands it to :func:`farm_v2.solver.solve_farm_v2`, and serialises the result. It is the seam where
a payload key becomes a solver argument, so a key read here and nowhere else is a feature with no
path in — the failure class this module has produced four times (W6's demand_at_cap_threshold,
city_water_cost, gap_note, city_water_fixed_fee). Every new money key needs a test that executes
THIS function, not one that inspects the solver.

It lived inside a JS template literal in index.html until E2. Deliberately importable and
matplotlib-free: the chart lives in farm_v2/charts.py so a server caller can run the money path
without shipping matplotlib. Nothing here draws.
"""
import json
import traceback

from farm_v2.solver import PLAN_STATUSES, solve_farm_v2
from farm_v2.utils.water import get_rainfall_weekly

# numpy is NOT imported here: the deleted heatmap was this file's only user of it, and the
# solver's arrays are read element-wise through float() below. The solver still needs numpy,
# and Pyodide still loads it — this adapter just does not touch it.


def run_from_js(params_json):
    try:
        p = json.loads(params_json)

        # A blanked numeric field arrives PRESENT with value None: parseFloat('') is NaN and
        # JSON.stringify(NaN) is 'null', so p.get(key, default) returns None — the default
        # never applies — and float(None) hands the grower a raw TypeError traceback instead
        # of a plan. Documented once at the sell-through fields and then reintroduced by every
        # other float(p.get(...)) line; this helper is the single place the rule lives now.
        def _num(key, default):
            v = p.get(key, default)
            return float(default if v is None else v)

        # For always-sent capacity/price boxes, a blanked value must be REFUSED, not
        # defaulted: _num's present-None→default turned a blanked storage box into an
        # "optimal" plan charging depreciation on the 1e9 no-constraint default (profit
        # −$25.9B), and a blanked tank box into $5.8k/yr of invented depreciation — both
        # were loud failures before. Same contract as well_weekly_cap_L below: ABSENT means
        # the documented default (toggle-off / server callers omitting the key); PRESENT
        # with None means the grower blanked a box whose value would otherwise be invented.
        def _num_no_invent(key, default):
            if key in p and p.get(key) is None:
                raise ValueError(f"{key} is blank in the payload: the value would be invented")
            return float(p.get(key, default))

        # --- Farm infrastructure ---
        total_land               = _num('total_land', 150)
        # Cash floor (C13) is only enforced when the UI cash toggle is on, which
        # is the only time opening_cash/credit_line are present in the payload.
        cash_constraint_enabled  = ('opening_cash' in p) or ('credit_line' in p)
        opening_cash             = _num('opening_cash', 0)
        credit_line              = _num('credit_line', 0)
        harvest_storage_cap      = _num_no_invent('harvest_storage_cap', 1e9)  # huge default = no constraint when toggle off
        equip_storage            = _num('equip_storage', 0)
        fuel_storage             = _num('fuel_storage', 0)
        water_storage_capacity   = _num_no_invent('water_storage_capacity', 500000)
        operating_weeks          = int(_num('operating_weeks', 52))   # deprecated: solver ignores it

        # --- Fixed cost rates ---
        rate_harvest_storage     = _num('rate_harvest_storage', 0.0)  # 0 = no storage cost
        rate_irrigation          = _num('rate_irrigation', 0.0)       # 0 = no irrigation cost
        rate_equip_storage       = _num('rate_equip_storage', 0.0)
        rate_fuel_storage        = _num('rate_fuel_storage', 0.0)
        rate_water_storage       = _num('rate_water_storage', 0.00360)
        rate_machinery           = _num('rate_machinery', 0.0)
        rate_property_mortgage_rent = _num('rate_property_mortgage_rent', 0.0)
        other_debt_service_per_week = _num('other_debt_service_per_week', 0.0)

        # --- Water ---
        climate_zone             = str(p.get('climate_zone', 'california_central_valley'))
        well_enabled             = bool(p.get('well_enabled', True))
        # No 2,500,000 fallback. That figure was a California water PERMIT used as a pump
        # capacity, retired in 667301d; leaving it as a default meant a payload without the key
        # silently got a farm that cannot irrigate itself. Same reasoning as TestNoPhantomFarm.
        if p.get('well_weekly_cap_L') in (None, ''):
            raise ValueError("no well_weekly_cap_L in payload: irrigation capacity would be invented")
        well_weekly_cap_L        = float(p['well_weekly_cap_L'])
        catchment_enabled        = bool(p.get('catchment_enabled', False))
        catchment_surface_area_m2 = _num_no_invent('catchment_surface_area_m2', 5000)
        city_water_enabled       = bool(p.get('city_water_enabled', False))
        city_water_cost_per_L    = _num_no_invent('city_water_cost_per_L', 0.003)
        # No form input exists for the standing charge yet, but the solver models it, the P&L
        # labels it, and imported/server payloads may carry it — without this line the feature
        # was silently $0 on every browser solve while its label and test made it look live.
        city_water_fixed_fee     = _num('city_water_fixed_fee_per_week', 0.0)

        # --- Variable costs ---
        cost_fert_per_lb         = _num('cost_fert_per_lb', 0.0)
        cost_fuel_per_L          = _num('cost_fuel_per_L', 0.0)

        # --- Realism factors (sell-through in-objective; overhead & interest below the line) ---
        sell_through_fraction    = _num('sell_through_fraction', 1.0)
        min_viable_margin_pct    = _num('min_viable_margin_pct', 0.0)   # 0 = hurdle off
        overhead_pct_of_revenue  = _num('overhead_pct_of_revenue', 0.0)
        interest_rate_apr        = _num('interest_rate_apr', 0.0)

        # --- Labor flexibility (Phase 5, Advanced; off by default = labor is fixed) ---
        labor_flex_enabled       = bool(p.get('labor_flex_enabled', False))
        hire_enabled             = labor_flex_enabled and bool(p.get('hire_enabled', True))
        max_hire_hrs_per_week    = _num('max_hire_hrs_per_week', 0.0)
        hire_wage_markup         = _num('hire_wage_markup', 0.0)
        # None means infer from the listed crew; 0 would mean free help (W15).
        overtime_flex_enabled    = labor_flex_enabled and bool(p.get('overtime_enabled', True))
        overtime_rate_multiplier = _num('overtime_rate_multiplier', 1.5)
        _max_ot                  = p.get('max_overtime_hrs_per_week', None)
        max_overtime_hrs_per_week = float(_max_ot) if _max_ot not in (None, '') else None

        # Payroll load: employer burden on top of wages (payroll taxes, workers' comp,
        # benefits, unemployment). Applied to every employee below as benefits_pct, so it
        # lifts both salaried fixed cost and the blended hourly rate — which means hired
        # and overtime hours inherit it automatically.
        payroll_load = max(0.0, _num('payroll_load_pct', 0.0))

        # A BASE wage, the same basis every other wage box uses. The payroll load is applied in
        # labor.py via hired_wage_load_pct (passed below), next to where every other wage gets
        # its load — this adapter used to multiply it here, which made the solver parameter
        # secretly mean 'all-in wage' and set up any direct/server caller to under-price hires.
        # Blank means infer. A typed 0/negative is refused — by the form validator before the
        # solve, and by validate_params for any non-browser caller. Neither silently rewrites it
        # to "infer", which is what this path used to do.
        _hw_raw                  = p.get('hired_wage_per_hr', None)
        hired_wage_per_hr        = None if _hw_raw in (None, '') else float(_hw_raw)

        rainfall = get_rainfall_weekly(climate_zone=climate_zone)

        # Phase 3.3: Monte Carlo rainfall multiplier pathway
        # JS passes rainfall_weekly_multipliers as a 52-element list of floats (one per week)
        _rain_mult = p.get('rainfall_weekly_multipliers', None)
        if isinstance(_rain_mult, list) and len(_rain_mult) == 52:
            rainfall = [max(0.0, float(rainfall[i]) * float(_rain_mult[i])) for i in range(52)]

        # --- Labor (dynamic positions from UI) ---
        # Present-None on employee numerics passes through UNCONVERTED so Step-0 validation
        # refuses it as invalid_input naming the role — float(None) here crashed into the
        # blanket except (a raw traceback), and defaulting it would silently zero someone's
        # pay or hours, the blank-wage class one dict deeper. Browser payloads cannot send
        # these nulls (getLaborFromForm coerces); this is for the server/LLM payload path.
        def _e_val(e, key, default, conv=float):
            v = e.get(key, default)
            return v if v is None else conv(v)

        year_round_employees = []
        seasonal_employees   = []
        for e in p.get('employees', []):
            t = e.get('type', 'hourly')
            pos = {
                "position":      str(e.get('position', 'Worker')),
                # float, not int: the What-If labor lever scales counts fractionally (+10% of
                # a 2-person crew is 2.2 workers-worth of hours). int() truncated 2.2 back to
                # 2, reintroducing the rounding no-op this line sits under one layer down.
                "count":         _e_val(e, 'count', 1),
                "type":          t if t != 'seasonal' else 'FT',
                "wage":          _e_val(e, 'wage', 0),
                "hours_per_week": _e_val(e, 'hours_per_week', 40),
                "field_time_pct": _e_val(e, 'field_time_pct', 100),
            }
            if t == 'seasonal':
                pos['start_week'] = _e_val(e, 'start_week', 1, conv=int)
                pos['end_week']   = _e_val(e, 'end_week', 52, conv=int)
                seasonal_employees.append(pos)
            else:
                year_round_employees.append(pos)

        # Fallback if no employees defined
        if not year_round_employees and not seasonal_employees:
            # Was: silently staff 28 people (1 manager, 2 operators, 15 field, 10 harvest) and
            # bill them. The worst of the three phantom fallbacks — labor is both a cost line
            # and a capacity constraint, so an unstated crew changes the plan AND the P&L.
            raise ValueError("no labor positions in payload: the plan's capacity and payroll "
                             "would both be invented")

        # Apply the farm-wide payroll load to every position (UI-defined and fallback).
        for _e in year_round_employees + seasonal_employees:
            _e["benefits_pct"] = payroll_load

        # --- Channels from UI ---
        channels_from_ui = p.get('channels', None)
        if not channels_from_ui:
            raise ValueError("no channels in payload: a farm with no way to sell is not a plan")
        channels = [{"name": ch['name']} for ch in channels_from_ui]

        # Variable selling cost per lb (deducted from net price per channel)
        ch_var_cost = {ch['name']: float(ch.get('variable_selling_cost_per_lb', 0))
                       for ch in (channels_from_ui or [])}
        # Fixed selling cost (informational only — not passed to solver, shown in results)
        ch_fixed_per_wk = sum(float(ch.get('fixed_selling_cost_per_wk', 0))
                              for ch in (channels_from_ui or []))

        # --- Crops (fully dynamic from UI) ---
        # No fallback. A payload without crops used to silently solve a stale 8-crop demo
        # (pre-b6bde4a, still carrying Napa Cabbage) and return a confident plan for a farm
        # nobody described. Unreachable from the app — every caller sends getCropsFromForm() —
        # but the server path is exactly where a phantom farm would be believed.
        ambient_storage_cap_v  = float(p.get('ambient_storage_cap', 0.0) or 0.0)
        rate_ambient_storage_v = float(p.get('rate_ambient_storage', 0.0) or 0.0)
        raw_crops = p.get('crops')
        if not raw_crops:
            raise ValueError("no crops in payload: refusing to solve a farm that was not described")
        # Subtract variable selling cost from each crop-channel price.
        # Normalise sales_spread_weeks: int 1-52 (the 8-week ceiling was lifted in B.3),
        # default 1 = sold in the harvest week under strict semantics.
        crops = []
        for crop in raw_crops:
            ac = dict(crop)
            if 'channels' in ac and ch_var_cost:
                adj = {}
                for ch_name, ch_data in ac['channels'].items():
                    d = dict(ch_data)
                    d['price_per_lb'] = max(0.0, float(d.get('price_per_lb', 0)) - ch_var_cost.get(ch_name, 0))
                    adj[ch_name] = d
                ac['channels'] = adj
            # int 1-52; missing/blank/0 → 1
            raw_spread = ac.get('sales_spread_weeks', 1)
            try:
                ac['sales_spread_weeks'] = max(1, min(52, int(raw_spread or 1)))
            except (TypeError, ValueError):
                ac['sales_spread_weeks'] = 1
            # Cold vs ambient. Default TRUE so a crop dict from anywhere that predates the flag
            # (saved plans, CSV imports, the chatbot) keeps the refrigerated behaviour it was
            # solved with, rather than silently moving to a barn that may have zero capacity.
            ac['cold_storage'] = bool(ac.get('cold_storage', True))
            crops.append(ac)

        # Pre-flight validation now lives inside solve_farm_v2 (Step 0), which is the point
        # every caller converges on — this adapter, the tests, and the server path. It returns
        # status 'invalid_input' with an 'errors' list, which the client already renders.

        result = solve_farm_v2(
            total_land=total_land,
            opening_cash=opening_cash,
            credit_line=credit_line,
            cash_constraint_enabled=cash_constraint_enabled,
            sell_through_fraction=sell_through_fraction,
            min_viable_margin_pct=min_viable_margin_pct,
            overhead_pct_of_revenue=overhead_pct_of_revenue,
            interest_rate_apr=interest_rate_apr,
            harvest_storage_cap=harvest_storage_cap,
            storage_loss_frac_per_week=float(p.get('storage_loss_frac_per_week', 0.0) or 0.0),
            ambient_storage_cap=ambient_storage_cap_v,
            rate_ambient_storage=rate_ambient_storage_v,
            operating_weeks=operating_weeks,
            rate_harvest_storage=rate_harvest_storage,
            rate_water_storage=rate_water_storage,
            rate_irrigation=rate_irrigation,
            rate_equip_storage=rate_equip_storage,
            rate_fuel_storage=rate_fuel_storage,
            rate_machinery=rate_machinery,
            rate_property_mortgage_rent=rate_property_mortgage_rent,
            other_debt_service_per_week=other_debt_service_per_week,
            fixed_selling_per_week=ch_fixed_per_wk,
            equip_storage=equip_storage,
            fuel_storage=fuel_storage,
            water_storage_capacity=water_storage_capacity,
            rainfall_weekly_L_per_acre=rainfall,
            well_enabled=well_enabled,
            well_weekly_cap_L=well_weekly_cap_L,
            catchment_enabled=catchment_enabled,
            catchment_surface_area_m2=catchment_surface_area_m2,
            city_water_enabled=city_water_enabled,
            city_water_cost_per_L=city_water_cost_per_L,
            city_water_fixed_fee_per_week=city_water_fixed_fee,
            cost_fert_per_lb=cost_fert_per_lb,
            cost_fuel_per_L=cost_fuel_per_L,
            year_round_employees=year_round_employees,
            seasonal_employees=seasonal_employees,
            hire_enabled=hire_enabled,
            max_hire_hrs_per_week=max_hire_hrs_per_week,
            hire_wage_markup=hire_wage_markup,
            hired_wage_per_hr=hired_wage_per_hr,
            hired_wage_load_pct=payroll_load,
            overtime_enabled=overtime_flex_enabled,
            overtime_rate_multiplier=overtime_rate_multiplier,
            max_overtime_hrs_per_week=max_overtime_hrs_per_week,
            crops=crops,
            channels=channels,
            solver_time_limit=75.0,
        )

        status = result['status']

        # 'time_limit_feasible' carries a real plan — HiGHS stopped on the clock with a
        # feasible incumbent rather than proving optimality (SPEC_v3 §7.1). Treat it as a
        # result and let the UI say so; bailing here would show "no solution found" while a
        # usable plan sits in the object.
        if status not in PLAN_STATUSES:
            # Carry the plural 'errors' through. invalid_input is the pre-flight guard
            # refusing the solve, and the reasons are the whole point of it; returning only
            # the singular 'error' here is how they got dropped once already.
            return json.dumps({
                'status': status,
                'error': result.get('message', 'Solver did not find an optimal solution.'),
                'errors': result.get('errors', []),
                'warnings': result.get('warnings', []),
                'profit': None,
            })

        # The solver's own arrays and tables, read element-wise below.
        x_sol  = result['x']
        y_sol  = result['y']
        succs  = result['successions']
        cr     = result['crops']

        profit       = float(result['profit'])
        operating_profit = float(result.get('operating_profit', result['profit']))
        overhead_cost = float(result.get('overhead_cost', 0.0))
        interest_cost = float(result.get('interest_cost', 0.0))
        sell_through_frac = float(result.get('sell_through_fraction', 1.0))
        revenue      = float(result['revenue'])
        variable_cost = float(result['variable_cost'])
        fixed_cost   = float(result['fixed_cost'])
        peak_borrow       = float(result['peak_borrowing'])
        weekly_cash_flow  = result.get('weekly_cash_flow', [])

        # Channel fixed-selling (market stall fees, distributor retainers): a real recurring cost
        # the optimizer does not allocate over. Deduct it below the line so net profit reflects it.
        fixed_selling_cost = ch_fixed_per_wk * 52          # annual: a market stall fee is a yearly commitment
        profit = profit - fixed_selling_cost

        # Succession schedule for Gantt calendar and pie chart
        sched = []
        for i, s in enumerate(succs):
            frac2 = float(x_sol[i])
            plt2  = int(round(float(y_sol[i])))
            if frac2 < 5e-4 and not plt2:
                continue
            sched.append({
                'name':   s['name'],
                'crop':   cr[s['crop']]['name'],
                'acres':  round(frac2 * total_land, 1),
                'weeks':  list(s['weeks']),
                'phases': list(s['phases']),
            })

        crop_names = [c['name'] for c in cr]

        # Weekly resource utilization for the constraint summary.
        #
        # These come from the SOLVER's capacity_series, not from a re-walk of the calendar
        # here. They are the exact used/cap pairs C2, C3 and C4b enforced. SPEC_v3 §9, audit
        # N5/N6: the client renders what the solver returns and never recomputes physics.
        #
        # The hand-rolled versions that used to live here disagreed with the model in ways
        # that mis-ranked the bottleneck, because the ranking picks the max utilisation ACROSS
        # these series:
        #   • water supply counted rain falling on fields, but C3 treats rain as a REDUCTION
        #     in demand (net_water_rate), not as supply — 1.5x too big on average on the
        #     shipped farm, 2.2x at peak;
        #   • labor supply summed raw crew hours and ignored field_time_pct — up to 16% high;
        #   • storage counted harvest INFLOW, which misses everything a crop holds after its
        #     harvest week.
        # Fixing one of the four would have made the ranking worse, not better.
        _cap = result.get('capacity_series', {})
        _z52 = [0.0] * 52
        weekly_harvest_vol  = list(_cap.get('storage', {}).get('used', _z52))
        weekly_water_used   = list(_cap.get('water', {}).get('used', _z52))
        weekly_water_supply = list(_cap.get('water', {}).get('cap', _z52))
        weekly_labor_used   = list(_cap.get('labor', {}).get('used', _z52))
        weekly_labor_supply = list(_cap.get('labor', {}).get('cap', _z52))

        weekly_land_frac = [0.0] * 52
        for i, s in enumerate(succs):
            frac2 = float(x_sol[i])
            if frac2 < 1e-6:
                continue
            for w in s['weeks']:
                if 1 <= w <= 52:
                    weekly_land_frac[w-1] += frac2

        # W1 / D4 — the REAL per-channel weekly sales schedule, off the solver's own 'v'.
        # The client used to rebuild this from gross harvest x demand x price, which ignored
        # sell-through, storage carry, the annual caps and the hurdle, so the pies, the sales
        # CSV and the P&L channel lines all disagreed with the headline revenue on the same
        # screen. Rounding is wire size only (2dp on pounds); the revenue figures are NOT
        # rounded, because the channel lines must still add up to 'revenue' exactly.
        channel_sales_out = {}
        for ch_name, ch_data in result.get('channel_sales', {}).items():
            by_crop = {}
            for cp_name, cp in ch_data['by_crop'].items():
                by_crop[cp_name] = {
                    'lbs_sold':   round(float(cp['lbs_sold']), 2),
                    'revenue':    float(cp['revenue']),
                    'weekly_lbs': [round(float(t), 2) for t in cp['weekly_lbs']],
                }
            channel_sales_out[ch_name] = {
                'lbs_sold': round(float(ch_data['lbs_sold']), 2),
                'revenue':  float(ch_data['revenue']),
                'by_crop':  by_crop,
            }

        return json.dumps({
            'status':        status,
            # SPEC_v3 §8 — forward the solver's own margin kernel so the UI renders these
            # numbers instead of recomputing them with rates the model never charges.
            'channel_margins':   result.get('channel_margins', {}),
            'crop_contribution': result.get('crop_contribution', {}),
            'excluded_channels': result.get('excluded_channels', []),
            'channel_sales': channel_sales_out,   # built above (W1 / D4)
            # W6 — demand saturation measured against the row the solver enforces. Forwarded
            # verbatim: the client used to rebuild the caps from the form (three separate
            # builders, one of which ASSIGNED overlapping demand ranges where the solver
            # accumulates them) and divide by a gross-harvest numerator. Nothing here is
            # recomputed in JS now, for the same reason channel_sales is not.
            'demand_saturation': result.get('demand_saturation', {}),
            # The threshold weeks_at_cap was measured at, so the CSV can head that column with
            # the number it actually used instead of asserting one. Forgetting this line is how
            # the field came to be undefined in the browser while the jsdom fixture supplied it
            # and every test passed.
            'demand_at_cap_threshold': float(result.get('demand_at_cap_threshold', 0.95)),
            # SPEC_v3 §9 — the inventory core's outputs. waste_by_crop is not optional
            # reporting: deleting C7 made overproduction legal rather than infeasible, so a
            # modelling bug now shows up as a plan that quietly dumps product instead of one
            # with visibly suppressed acreage.
            'waste_by_crop':     result.get('waste_by_crop', {}),
            'storage_peak_m3':   float(result.get('storage_peak_m3', 0.0)),
            # Ambient (barn) is a second pool with its own cap and its own depreciation line;
            # a farm can be comfortable in the cooler and out of barn space, or the reverse.
            'ambient_peak_m3':   float(result.get('ambient_peak_m3', 0.0)),
            'ambient_cap_m3':    float(_cap.get('storage_ambient', {}).get('cap', [0.0])[0]),
            'profit':        profit,
            'operating_profit': operating_profit,
            'overhead_cost': overhead_cost,
            'interest_cost': interest_cost,
            'fixed_selling_cost': fixed_selling_cost,
            'sell_through_fraction': sell_through_frac,
            'revenue':       revenue,
            'variable_cost': variable_cost,
            'fixed_cost':    fixed_cost,
            # W4 — the two cost breakdowns the P&L prints under these totals, forwarded verbatim
            # from the solver, which sums each total FROM its own split. Everything the P&L used
            # to ask for was computed here or in the solver and never sent: twelve of thirteen
            # detail keys arrived as None, and the thirteenth was gated on "> 0" at zero. Two
            # derivations went with them — "cost_property" (the same annualisation the solver
            # already does, done twice) and "cost_ambient_storage", which was emitted with a
            # comment saying the fixed-cost breakdown needed it and was read by nothing at all.
            'variable_cost_split': result.get('variable_cost_split', {}),
            'fixed_cost_split':    result.get('fixed_cost_split', {}),
            # The three operating costs that sit OUTSIDE both totals above, each with its own P&L
            # row. city_water_cost was the one this fix nearly shipped without: the solver charges
            # it into operating_profit, so a row reading a key the adapter never sent would print
            # 0.00 AND push the difference into the new UNRECONCILED tripwire on every farm that
            # buys metered water. The golden farm has city water off and the jsdom fixture
            # supplied the key itself, so nothing would have failed. Same mechanism as W6's
            # demand_at_cap_threshold, one release later.
            'city_water_cost':      float(result.get('city_water_cost', 0.0)),
            'labor_flex_enabled':   bool(result.get('labor_flex_enabled', False)),
            'hire_cost':            float(result.get('hire_cost', 0.0)),
            'overtime_cost':        float(result.get('overtime_cost', 0.0)),
            'total_hired_hours':    float(result.get('total_hired_hours', 0.0)),
            'total_overtime_hours': float(result.get('total_overtime_hours', 0.0)),
            'hired_hours_weekly':    [round(float(v), 1) for v in result.get('hired_hours_weekly', [])],
            'overtime_hours_weekly': [round(float(v), 1) for v in result.get('overtime_hours_weekly', [])],
            # The prices those hours were (or would be) bought at, $/hr all-in — 52 entries,
            # 0-indexed. Forwarded so renderLaborPlan can print a number the grower can check
            # against their local market instead of a description of an inference.
            'hire_rate_full_weekly':     [round(float(v), 2) for v in result.get('hire_rate_full_weekly', [])],
            'overtime_rate_full_weekly': [round(float(v), 2) for v in result.get('overtime_rate_full_weekly', [])],
            'peak_borrowing': peak_borrow,
            'succession_schedule': sched,
            'crop_names':          crop_names,
            'weekly_land_frac':    [round(v, 4) for v in weekly_land_frac],
            'weekly_harvest_vol':  [round(v, 2) for v in weekly_harvest_vol],
            'weekly_water_used':   [round(v, 0) for v in weekly_water_used],
            'weekly_water_supply': weekly_water_supply,
            'weekly_labor_used':   [round(v, 1) for v in weekly_labor_used],
            'weekly_labor_supply': weekly_labor_supply,
            'weekly_cash_flow':    [round(float(v), 0) for v in weekly_cash_flow] if len(weekly_cash_flow) > 0 else [],
            'opening_cash':        opening_cash,
            'credit_line':         credit_line,
            # Pre-flight findings from validate.py (S1). Carried on every successful solve,
            # including the What-If / sensitivity / Monte Carlo paths, because they all come
            # through here and none of them passes the browser's validateParams().
            'warnings': result.get('warnings', []),
            # "Stopped at the time limit — best plan found, not a proven optimum." The browser
            # has read this key since the time limit shipped; the adapter never sent it, so the
            # one warning that matters most on a truncated solve could never display and a
            # 75-second farm rendered exactly like a proven-optimal one. Fourth instance of the
            # solver-adds-field-adapter-doesn't class (W6, city_water_cost, gap_note).
            'gap_note': result.get('gap_note'),
            # Why each requested crop is absent from the plan (S2).
            'unplanted_crops': result.get('unplanted_crops', []),
        })

    except Exception as e:
        tb = traceback.format_exc()
        return json.dumps({'status': 'error', 'error': str(e) + '\n\n' + tb})
