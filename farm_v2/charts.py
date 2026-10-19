"""charts.py — presentation only, and the only farm_v2 module that imports matplotlib.

Split out of the adapter by E2. The money path (farm_v2/adapter.py) must never import this:
a server caller runs the solve and the accounting without a plotting stack, and the sweep paths
(What-If, sensitivity, Monte Carlo, diagnostic replay) never wanted an image in the first place.

``waterfall_png(result_json)`` takes the JSON that run_from_js returned — every value the
waterfall needs is already in it — so drawing is a second, optional call by whoever renders,
not a cost every solve pays. It is deliberately NOT named `*_from_js`: the point of this module
is that the caller need not be a browser.
"""
import base64
import io
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from farm_v2.solver import PLAN_STATUSES


def _fig_to_b64(fig, dpi):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return b64


def make_waterfall_chart(revenue, variable_cost, fixed_cost, overhead_cost, interest_cost, selling_cost, profit,
                         bought_cost=0.0):
    # Page-palette colors: green revenue, red/amber costs, green/red profit.
    # profit is NET (after overhead + interest + selling). Below-the-line rows appear only when nonzero.
    c_green = '#2d6a4f'; c_red = '#dc2626'; c_amber = '#b45309'
    labels = ['Revenue', 'Variable Cost', 'Fixed Cost']
    values = [revenue, -variable_cost, -fixed_cost]
    colors = [c_green, c_red, c_amber]
    # City water, overtime and hire sit OUTSIDE both cost totals (W8's bought_capacity_split).
    # Without this bar a farm buying any of them drew bars that did not add up to Net Profit.
    if bought_cost >= 5000:
        labels.append('Bought Capacity'); values.append(-bought_cost); colors.append(c_amber)
    if selling_cost >= 5000:    # only show material lines (avoids a "$0.00M" sliver)
        labels.append('Selling');   values.append(-selling_cost);   colors.append(c_amber)
    if overhead_cost >= 5000:
        labels.append('Overhead');  values.append(-overhead_cost);  colors.append(c_amber)
    if interest_cost >= 5000:
        labels.append('Interest');  values.append(-interest_cost);  colors.append(c_amber)
    labels.append('Net Profit');    values.append(profit);          colors.append(c_green if profit >= 0 else c_red)
    widths  = [abs(v) / 1e6 for v in values]
    n = len(labels); bar_h = 0.48; x_max = max(widths) * 1.30

    fig, ax = plt.subplots(figsize=(5.5, max(2.4, 0.45 * n + 0.6)))
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#f9fafb')

    # Draw rounded bars top→bottom in declared order (Revenue at top, Net Profit
    # at bottom). Row i sits at yi=n-1-i; y-tick labels are reversed to match.
    for i, (w, col) in enumerate(zip(widths, colors)):
        yi   = n - 1 - i
        pad  = 0.04
        w_in = max(0.001, w - pad)
        h_in = bar_h - 2 * pad
        patch = mpatches.FancyBboxPatch(
            (0, yi - bar_h / 2 + pad), w_in, h_in,
            boxstyle=f'round,pad={pad}',
            facecolor=col, edgecolor='none', zorder=2,
        )
        ax.add_patch(patch)
        val   = values[i]
        sign  = '+$' if val >= 0 else '-$'
        ax.text(w + x_max * 0.015, yi,
                f"{sign}{abs(val)/1e6:.2f}M",
                va='center', ha='left', fontsize=8, fontweight='600',
                color='#374151', zorder=3)

    ax.set_yticks(list(range(n)))
    ax.set_yticklabels(labels[::-1], fontsize=9, color='#374151')
    ax.set_xlim(0, x_max)
    ax.set_ylim(-0.65, n - 0.35)
    ax.set_xlabel('USD (millions)', fontsize=8, color='#9ca3af')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#e5e7eb')
    ax.tick_params(axis='y', length=0, labelsize=9)
    ax.tick_params(axis='x', labelsize=8, labelcolor='#9ca3af', color='#e5e7eb')
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color='#e5e7eb', linewidth=0.5, zorder=0)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig, dpi=150)


def waterfall_png(result_json):
    """Base64 PNG of the profit waterfall for a run_from_js result; '' when there is no plan.

    Reads the same seven figures the adapter used to pass positionally. `profit` is the NET
    number AFTER the fixed-selling deduction and `fixed_selling_cost` is that deduction, which
    is why both are taken off the result rather than recomputed — the solver owns money and
    this module renders it.

    Every figure is required, not `.get`-with-a-default: the adapter emits all seven
    unconditionally, so a missing one is a broken contract and a KeyError is the right
    loudness. Defaulting on BOTH sides of the boundary is how this repo's four documented
    "solver adds a field, adapter doesn't" false-greens each stayed quiet — and the chart is
    the artifact a grower screenshots, so a silently dropped row is the worst place for it.
    """
    r = json.loads(result_json)
    if r.get('status') not in PLAN_STATUSES:
        return ''
    return make_waterfall_chart(
        float(r['revenue']),
        float(r['variable_cost']),
        float(r['fixed_cost']),
        float(r['overhead_cost']),
        float(r['interest_cost']),
        float(r['fixed_selling_cost']),
        float(r['profit']),
        float(sum(r['bought_capacity_split'].values())),
    )
