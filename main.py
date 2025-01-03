import datetime
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from typing import List, Optional
import csv
import os
import argparse
import json
from pathlib import Path


@dataclass_json
@dataclass
class Strategy:
    """
    Represents an allocation of income towards different financial goals.

    This class is used to model the percentage of income allocated to three categories:
    - Home loan repayment
    - Student loan repayment
    - Investing

    The sum of `home_loan` and `student_loan` should not exceed 100%. The `investing`
    allocation is automatically calculated as the remaining percentage of the total (i.e.,
    100% - (home_loan + student_loan)).

    Attributes:
        home_loan (float): The percentage of income allocated to home loan repayment.
        student_loan (float): The percentage of income allocated to student loan repayment.
        investing (float): The percentage of income allocated to investing, automatically
                            calculated to ensure the total allocation is 100%.

    Raises:
        ValueError: If the sum of `home_loan` and `student_loan` exceeds 100%.
    """

    home_loan: float
    student_loan: float
    investing: Optional[float] = None

    def __post_init__(self):

        if not self.investing:
            self.investing = 100.0 - (self.home_loan + self.student_loan)

        if not (0 <= self.investing <= 100):
            raise ValueError(
                f"Invalid strategy. Strategies must be percentages that sum to less than 100. Got: {self.home_loan}, {self.student_loan}."
            )

    def generate_output_filename(self) -> str:
        home_loan_str = f"{self.home_loan:g}"
        student_loan_str = f"{self.student_loan:g}"
        investing_str = f"{self.investing:g}"
        filename = f"home_{home_loan_str}_student_{student_loan_str}_investing_{investing_str}.csv"
        safe_filename = filename.replace(":", "_").replace(" ", "_")
        return safe_filename


@dataclass_json
@dataclass
class InitialConditions:
    home_loan_initial_balance: float
    home_loan_interest_rate: float
    home_loan_minimum_repayment: float
    student_loan: float
    student_loan_indexation_rate: float
    fortnightly_student_loan_tax: float
    initial_fortnightly_spare_cash: float
    wage_growth_rate: float
    investment_growth_rate: float
    investment_distribution_rate: float


@dataclass_json
@dataclass
class SimulationConfig:
    initial_conditions: InitialConditions
    strategies: List[Strategy]
    start_date: datetime.date
    end_date: datetime.date


@dataclass
class SimulationState:
    home_loan_balance: float
    student_loan_balance: float
    distribution_balance: float
    portfolio_value: float
    fortnightly_spare_cash: float

    @classmethod
    def from_config(cls, config: InitialConditions) -> "SimulationState":

        return cls(
            home_loan_balance=config.home_loan_initial_balance,
            student_loan_balance=config.student_loan,
            distribution_balance=0.0,
            portfolio_value=0.0,
            fortnightly_spare_cash=config.initial_fortnightly_spare_cash,
        )

    def apply_home_loan_interest(self, config: InitialConditions):
        interest_rate = config.home_loan_interest_rate / 12
        interest = self.home_loan_balance * interest_rate
        self.home_loan_balance += interest

    def apply_minimum_mortgage_repayment(self, config: InitialConditions):
        if self.home_loan_balance > 0:
            self.home_loan_balance -= config.home_loan_minimum_repayment

    def apply_minimum_student_loan_repayment(self, config:InitialConditions):
        if self.student_loan_balance > 0:
            self.student_loan_balance -= config.fortnightly_student_loan_tax*26

    def apply_strategy(self, strategy: Strategy, config: InitialConditions):

        cash_to_use = self.fortnightly_spare_cash

        if self.home_loan_balance <= 0:
            cash_to_use += config.home_loan_minimum_repayment

        if self.student_loan_balance <= 0:
            cash_to_use += config.fortnightly_student_loan_tax

        self.home_loan_balance -= strategy.home_loan / 100.0 * cash_to_use
        self.student_loan_balance -= strategy.student_loan / 100.0 * cash_to_use
        self.portfolio_value += strategy.investing / 100.0 * cash_to_use

    def grow_wage(self, config: InitialConditions):
        self.fortnightly_spare_cash = self.fortnightly_spare_cash * (
            1 + config.wage_growth_rate
        )

    def reindex_student_loan(self, config: InitialConditions):
        self.student_loan_balance = self.student_loan_balance * (
            1 + config.student_loan_indexation_rate
        )

    def apply_distributions(self, config: InitialConditions):

        distribution_rate = config.investment_distribution_rate / 4
        self.distribution_balance += self.portfolio_value * distribution_rate


@dataclass_json
@dataclass
class SimulationResult:
    config: InitialConditions
    strategy: Strategy
    net_worth: float
    final_state: SimulationState


@dataclass
class ActionDayFlags:
    payday: bool = False
    mortgage_repayment_day: bool = False
    first_of_the_month: bool = False
    first_of_the_quarter: bool = False
    pay_rise: bool = False
    student_loan_reindexation_day: bool = False
    student_loan_minimum_repayment_applied: bool = False 
    

    def __init__(self, start_date: datetime.date, current_date: datetime.date):

        days_since_start = (current_date - start_date).days

        if current_date.weekday() == 2 and (days_since_start % 14) > 6:
            self.payday = True

        if current_date.weekday() == 3:
            self.mortgage_repayment_day = True

        if current_date.day == 1:

            self.first_of_the_month = True

            if current_date.month % 3 == 1:
                self.first_of_the_quarter = True

            if current_date.month == 3:
                self.pay_rise = True
            elif current_date.month == 6:
                self.student_loan_reindexation_day = True
            elif current_date.month == 7:
                self.student_loan_minimum_repayment_applied = True 


def datetime_parser(dct):
    for key, value in dct.items():
        if isinstance(value, str):
            try:
                dct[key] = datetime.datetime.fromisoformat(value)
            except ValueError:
                pass
    return dct


def save_simulation_state_to_csv(
    state: SimulationState, date: datetime.datetime, filename: str
):

    with open(filename, mode="a", newline="") as file:
        writer = csv.writer(file)

        file.seek(0, 2)  # Move to the end of the file
        if file.tell() == 0:  # File is empty
            writer.writerow(
                [
                    "date",
                    "home_loan_balance",
                    "student_loan_balance",
                    "distribution_balance",
                    "portfolio_value",
                    "fortnightly_spare_cash",
                ]
            )

        writer.writerow(
            [
                date.isoformat(),
                state.home_loan_balance,
                state.student_loan_balance,
                state.distribution_balance,
                state.portfolio_value,
                state.fortnightly_spare_cash,
            ]
        )


def compute_net_worth(state: SimulationState, config: InitialConditions):

    equity = config.home_loan_initial_balance - state.home_loan_balance

    return (equity + state.portfolio_value + state.distribution_balance) - (
        state.home_loan_balance + state.student_loan_balance
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Parse configuration file")
    parser.add_argument(
        "--config",
        type=Path,
        default="config.json",
        help="Path to the configuration JSON file",
    )
    args = parser.parse_args()

    with open(args.config, "r") as file:
        c = file.read()
        config_dict = json.loads(c, object_hook=datetime_parser)
        config = SimulationConfig.from_dict(config_dict)

    print(f"Loaded config: {config}")

    results = []
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    timestampedFolder = os.path.join(results_dir, timestamp)

    os.makedirs(timestampedFolder, exist_ok=True)

    for defaultStrategy in config.strategies:

        outputFolder = os.path.join(
            timestampedFolder, defaultStrategy.generate_output_filename()
        )
        os.makedirs(outputFolder)

        state = SimulationState.from_config(config.initial_conditions)

        current_date = config.start_date

        while current_date <= config.end_date:
            flags = ActionDayFlags(config.start_date, current_date)

            if flags.mortgage_repayment_day:
                state.apply_minimum_mortgage_repayment(config.initial_conditions)

            if flags.payday:

                if state.home_loan_balance > 0:
                    if state.student_loan_balance > 0:
                        strategy = defaultStrategy
                    else:
                        strategy = Strategy(
                            home_loan=defaultStrategy.home_loan
                            + defaultStrategy.student_loan / 2,
                            student_loan=0,
                        )
                else:
                    if state.student_loan_balance > 0:
                        strategy = Strategy(
                            home_loan=0,
                            student_loan=defaultStrategy.student_loan
                            + defaultStrategy.home_loan / 2,
                        )
                    else:
                        strategy = Strategy(home_loan=0, student_loan=0)

                state.apply_strategy(strategy, config.initial_conditions)

            if flags.first_of_the_month:

                state.apply_home_loan_interest(config.initial_conditions)

                if flags.pay_rise:

                    state.grow_wage(config.initial_conditions)

                elif flags.student_loan_reindexation_day:

                    state.reindex_student_loan(config.initial_conditions)

                elif flags.student_loan_minimum_repayment_applied:

                    state.apply_minimum_student_loan_repayment(config.initial_conditions)

                if flags.first_of_the_quarter:

                    state.apply_distributions(config.initial_conditions)

                

            save_simulation_state_to_csv(state, current_date, os.path.join(outputFolder, "data.csv"))
            current_date += datetime.timedelta(days=1)

        result = SimulationResult(
            config=config.initial_conditions,
            strategy=defaultStrategy,
            net_worth=compute_net_worth(state, config.initial_conditions),
            final_state=state,
        )

        results.append(result)

        with open(os.path.join(outputFolder, "result.json"), "w") as f:
            f.write(result.to_json())

    best_result = max(results, key=lambda obj: obj.net_worth)

    print(
        f"Strategy with the highest net worth ({best_result.net_worth}): {best_result.strategy}"
    )
