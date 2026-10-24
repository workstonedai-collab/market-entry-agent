"""Deterministic single-currency scenario arithmetic; all values come from the operator."""
from decimal import Decimal, InvalidOperation
from functools import reduce
from .business import fields, text, identifier

ITEMS=('quantity','unit_price','unit_cost','freight','insurance','customs_value','duty_rate','channel_fee','fixed_cost','recoverable_tax')


def normalize(data):
    fields(data,['option_id','name','currency','unit','values'])
    values=data.get('values');fields(values,ITEMS)
    out={'option_id':identifier(data.get('option_id')),'name':text(data.get('name'),200),
         'currency':text(data.get('currency'),3).upper(),'unit':text(data.get('unit'),64),'values':{}}
    if len(out['currency'])!=3 or not out['currency'].isascii() or not out['currency'].isalpha():raise ValueError('Use one three-letter currency; no implicit FX conversion')
    for key in ITEMS:
        row=values.get(key)
        if row is None:out['values'][key]=None;continue
        fields(row,['value','basis','note'])
        if row.get('basis') not in ('operator_quote','assumption'):raise ValueError('Each numeric value needs operator_quote or assumption')
        value=row.get('value')
        if type(value) not in (int,float,str) or len(str(value))>40:raise ValueError('Use a bounded decimal value or null')
        try:number=Decimal(str(value))
        except InvalidOperation:raise ValueError('Invalid decimal value') from None
        if not number.is_finite() or not 0<=number<=Decimal('1000000000000'):raise ValueError('Values must be finite and nonnegative')
        if key=='quantity' and number==0:raise ValueError('Quantity must be positive')
        if key=='duty_rate' and number>1:raise ValueError('duty_rate is a fraction between zero and one')
        out['values'][key]={'value':str(number),'basis':row['basis'],'note':text(row.get('note'),500)}
    return out


def calculate(data):
    values=data['values'];numbers={key:(Decimal(row['value']) if row else None) for key,row in values.items()}
    def product(*keys):return None if any(numbers[k] is None for k in keys) else reduce(lambda a,b:a*b,(numbers[k] for k in keys),Decimal(1))
    def total(*parts):return None if any(p is None for p in parts) else sum(parts,Decimal(0))
    revenue=product('quantity','unit_price');goods=product('quantity','unit_cost');duty=product('customs_value','duty_rate')
    operating=total(goods,numbers['freight'],numbers['insurance'],duty,numbers['channel_fee'],numbers['fixed_cost'])
    contribution=None if revenue is None or operating is None else revenue-operating
    cash=total(operating,numbers['recoverable_tax'])
    metrics={'revenue':revenue,'goods_cost':goods,'duty':duty,'operating_cost':operating,'contribution_before_other_costs':contribution,
             'cash_outlay_including_recoverable_tax':cash,'contribution_margin':None if revenue in (None,0) or contribution is None else contribution/revenue}
    return {'currency':data['currency'],'unit':data['unit'],'metrics':{k:str(v) if v is not None else None for k,v in metrics.items()},
            'missing':[k for k,v in values.items() if v is None], 'assumptions':[k for k,v in values.items() if v and v['basis']=='assumption'],
            'formula':'revenue=quantity*unit_price; duty=operator customs_value*duty_rate; operating=quantity*unit_cost+freight+insurance+duty+channel_fee+fixed_cost; contribution=revenue-operating',
            'note':'Scenario arithmetic, not a verified quotation, customs valuation, tax opinion or net-profit forecast. All amounts use the one stated currency; recoverable tax is cash outlay, not deducted as an operating expense. Missing is null; zero requires an explicit value.'}
