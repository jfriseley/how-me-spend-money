import datetime
from dataclasses import dataclass
from dataclasses_json import dataclass_json
import csv
import argparse
import json
from pathlib import Path

START_DATE = datetime.date(2025, 1, 1)
END_DATE = datetime.date(2030, 12, 31)


@dataclass_json
@dataclass
class SimulationConfig:
    home_loan_initial_balance: float
    home_loan_interest_rate: float
    home_loan_minimum_repayment: float
    student_loan: float
    student_loan_indexation_rate: float
    initial_fortnightly_spare_cash: float
    wage_growth_rate: float
    investment_growth_rate: float
    investment_distribution_rate: float
    start_date: datetime.date = None
    end_date: datetime.date = None


@dataclass
class Allocation:
    home_loan: float
    student_loan: float
    investing: float = 0.0

    def __post_init__(self):
        self.investing = 100.0 - (self.home_loan + self.student_loan)

        if not (0 <= self.investing <= 100):
            raise ValueError(
                f"Invalid allocation. Allocations must be percentages that sum to less than 100. Got: {self.home_loan}, {self.student_loan}."
            )

    def generate_output_filename(self) -> str:
        home_loan_str = f"{self.home_loan:g}"
        student_loan_str = f"{self.student_loan:g}"
        investing_str = f"{self.investing:g}"
        filename = f"allocation_home_{home_loan_str}_student_{student_loan_str}_investing_{investing_str}.csv"
        safe_filename = filename.replace(":", "_").replace(" ", "_")
        return safe_filename


@dataclass
class SimulationState:
    home_loan_balance: float
    student_loan_balance: float
    distribution_balance: float
    portfolio_value: float
    fortnightly_spare_cash: float

    @classmethod
    def from_config(cls, config: SimulationConfig) -> "SimulationState":

        return cls(
            home_loan_balance=config.home_loan_initial_balance,
            student_loan_balance=config.student_loan,
            distribution_balance=0.0,
            portfolio_value=0.0,
            fortnightly_spare_cash=config.initial_fortnightly_spare_cash,
        )

    def apply_home_loan_interest(self, config: SimulationConfig):
        interest_rate = config.home_loan_interest_rate / 12
        interest = self.home_loan_balance * interest_rate
        self.home_loan_balance += interest

    def apply_minimum_mortgage_repayment(self, config: SimulationConfig):
        if self.home_loan_balance > 0:
            self.home_loan_balance -= config.home_loan_minimum_repayment

    def apply_allocation(self, allocation: Allocation, config: SimulationConfig):

        if self.home_loan_balance > 0:
            cash_to_use = self.fortnightly_spare_cash
        else:
            cash_to_use = (
                self.fortnightly_spare_cash + config.home_loan_minimum_repayment
            )

        if self.student_loan_balance <= 0:
            cash_to_use *= 1.08

        self.home_loan_balance -= allocation.home_loan / 100.0 * cash_to_use
        self.student_loan_balance -= allocation.student_loan / 100.0 * cash_to_use
        self.portfolio_value += allocation.investing / 100.0 * cash_to_use

    def grow_wage(self, config: SimulationConfig):
        self.fortnightly_spare_cash = self.fortnightly_spare_cash * (
            1 + config.wage_growth_rate
        )

    def reindex_student_loan(self, config: SimulationConfig):
        self.student_loan_balance = self.student_loan_balance * (
            1 + config.student_loan_indexation_rate
        )

    def apply_distributions(self, config: SimulationConfig):

        distribution_rate = config.investment_distribution_rate / 4
        self.distribution_balance += self.portfolio_value * distribution_rate


@dataclass
class ActionDayFlags:
    payday: bool = False
    mortgage_repayment_day: bool = False
    first_of_the_month: bool = False
    first_of_the_quarter: bool = False
    march_1st: bool = False
    june_1st: bool = False

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
                self.march_1st = True
            elif current_date.month == 6:
                self.june_1st = True


def save_simulation_state_to_csv(state: SimulationState, filename: str):

    with open(filename, mode="a", newline="") as file:
        writer = csv.writer(file)

        file.seek(0, 2)  # Move to the end of the file
        if file.tell() == 0:  # File is empty
            writer.writerow(
                [
                    "home_loan_balance",
                    "student_loan_balance",
                    "distribution_balance",
                    "portfolio_value",
                    "fortnightly_spare_cash",
                ]
            )

        writer.writerow(
            [
                state.home_loan_balance,
                state.student_loan_balance,
                state.distribution_balance,
                state.portfolio_value,
                state.fortnightly_spare_cash,
            ]
        )


def compute_net_worth(state: SimulationState, config: SimulationConfig):

    equity = config.home_loan_initial_balance - state.home_loan_balance

    return (equity + state.portfolio_value + state.distribution_balance) - (
        state.home_loan_balance + state.student_loan_balance
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Parse configuration file")
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to the configuration JSON file"
    )
    args = parser.parse_args()

    with open(args.config, "r") as file:
        config_dict = json.load(file)
        config = SimulationConfig.from_dict(config_dict)

    print(f"Loaded config: {config}")

    config.start_date = START_DATE
    config.end_date = END_DATE

    current_date = config.start_date

    allocations = [
        Allocation(home_loan=100, student_loan=0),
        Allocation(home_loan=0, student_loan=100),
        Allocation(home_loan=50, student_loan=30),
        Allocation(home_loan=20, student_loan=30),
    ]

    net_worths = []

    for defaultAllocation in allocations:
        print(f"Allocation: {defaultAllocation}")
        outputFile = defaultAllocation.generate_output_filename()
        state = SimulationState.from_config(config)
        print(f"Initial simulation state: {state}")
        current_date = config.start_date
        while current_date <= config.end_date:
            flags = ActionDayFlags(config.start_date, current_date)

            if flags.mortgage_repayment_day:
                state.apply_minimum_mortgage_repayment(config)

            if flags.payday:

                if state.home_loan_balance > 0:
                    if state.student_loan_balance > 0:
                        allocation = defaultAllocation
                    else:
                        allocation = Allocation(
                            home_loan=defaultAllocation.home_loan
                            + defaultAllocation.student_loan / 2,
                            student_loan=0,
                        )
                else:
                    if state.student_loan_balance > 0:
                        allocation = Allocation(
                            home_loan=0,
                            student_loan=defaultAllocation.student_loan
                            + defaultAllocation.home_loan / 2,
                        )
                    else:
                        allocation = Allocation(home_loan=0, student_loan=0)

                state.apply_allocation(allocation, config)

            if flags.first_of_the_month:

                state.apply_home_loan_interest(config)

                if flags.march_1st:

                    state.grow_wage(config)

                elif flags.june_1st:

                    state.reindex_student_loan(config)

                if flags.first_of_the_quarter:

                    state.apply_distributions(config)

            save_simulation_state_to_csv(state, outputFile)
            current_date += datetime.timedelta(days=1)

        print(f"Final simulation state: {state}")

        net_worth = compute_net_worth(state, config)
        print(f"Final net worth: {net_worth}")
        net_worths.append(net_worth)
        print()
        print()

    max_net_worth = max(net_worths)

    max_net_worth_index = net_worths.index(max_net_worth)

    print(
        f"Allocation with the highest net worth ({max_net_worth}): {allocations[max_net_worth_index]}"
    )
