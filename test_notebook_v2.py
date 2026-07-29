"""Test: execute all code cells of farm_optimization_v2.ipynb."""
import sys, os, json
sys.path.insert(0, '.')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import warnings
warnings.filterwarnings('ignore')
import pandas as pd

with open('farm_optimization_v2.ipynb') as f:
    nb = json.load(f)

globs = {'__name__': '__main__'}

for cell_num, cell in enumerate(nb['cells']):
    if cell['cell_type'] != 'code':
        continue
    src = ''.join(cell['source'])
    # Skip the os.chdir check (already in correct directory)
    src = src.replace(
        "os.path.basename(os.getcwd()) != 'excel-app'", 'False'
    )
    # Replace IPython display() with print()
    src = src.replace('display(', 'print(')
    try:
        exec(compile(src, 'cell_%d' % cell_num, 'exec'), globs)
    except Exception as e:
        print('ERROR in cell %d: %s: %s' % (cell_num, type(e).__name__, e))
        print('Source snippet:', src[:300])
        sys.exit(1)

print()
print('ALL NOTEBOOK CELLS EXECUTED SUCCESSFULLY')
result = globs.get('result', {})
if result.get('status') == 'optimal':
    print('Profit : $%s' % '{:,.0f}'.format(result['profit']))
    print('Revenue: $%s' % '{:,.0f}'.format(result['revenue']))
    print('VarCost: $%s' % '{:,.0f}'.format(result['variable_cost']))
    print('FixCost: $%s' % '{:,.0f}'.format(result['fixed_cost']))
