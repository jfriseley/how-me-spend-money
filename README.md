# Cash distribution simulation

This simulation determines the optimal way to distribute cash between three goals: paying off the mortgage, paying off a student loan and investing. The strategy it computes is optimal in the sense of final net worth, defined as:

(equity + investment portfolio + dividends) - (home loan + student loan)

# Running the simulation 

```
pip install -r requirements.txt
python main.py
```

# Simulation dynamics

- Spare cash is allocated to goals fortnightly
- Minimum mortgage repayments are weekly
- Wage growth is yearly
- Student loans are indexed yearly
- Interest on the home loan accrues monthly

# Assumptions

- Once the student loan is paid of, an amount of money `SimulationConfig.fortnightly_student_loan_tax` is added to fortnightly spare cash.
- Once the home loan is paid off, the minimum repayment is added to fortnightly spare cash.
- If one loan is paid off, the cash that would have gone toward it is split evenly between the remaining two goals. If both loans are paid off, all cash goes towards investing.
- Dividends from investments do not earn interest and are not re-invested.
- Equity is defined as initial house price minus home loan balance. This simulation does not factor in growth in the housing market.