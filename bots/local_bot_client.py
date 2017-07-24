import json
from threading import Thread, Event
import numpy as np

from utils.utils import Logger


class HotellingLocalBots(Logger, Thread):

    name = "HotellingLocalBots"

    with open("hotelling_server/parameters/game.json") as f:
        game_parameters = json.load(f)

    def __init__(self, controller, n_firms, n_customers, n_agents_to_wait):
        super().__init__()

        self.controller = controller
        self.time_manager = controller.time_manager
        self.data = controller.data

        self.n_positions = self.game_parameters["n_positions"]

        self.n_customers = n_customers
        self.n_firms = n_firms
        self.n_agents_to_wait = n_agents_to_wait

        self.customer_attributes = {}
        self.firm_attributes = {}

        self.customer_attributes["extra_view_possibilities"] = np.arange(0, self.n_positions - 1)
        self.firm_attributes["n_prices"] = self.game_parameters["n_prices"]

    def run(self):

        while True:

            # if all non bot agents are connected break
            non_bots = self.get_non_bot_agents()
            cond = len(non_bots) == self.n_agents_to_wait

            if cond:
                break

            if not self.controller.server.is_alive():
                return 0

        # start to init bots
        self.init()

        self.log("Local Bots: Game is starting.")

        while True:

            for firm_id in self.data.bot_firms_id.values():

                if self.data.current_state["firm_states"][firm_id] == "active":
                    self.play_active_firm(firm_id)

                else:
                    self.play_passive_firm()

                self.data.save()

            for customer_id in self.data.bot_customers_id.values():
                self.play_customer(customer_id)
                self.data.save()

            self.time_manager.check_state()

            Event().wait(1)

            if self.time_manager.state == "beginning_time_step" and self.time_manager.ending_t \
                or not self.controller.server.is_alive():
                    self.log("Local Bots: Game ends! Bots shutdown!")
                    break

    def get_non_bot_agents(self):

        all_agents = list(self.data.firms_id.items()) + list(self.data.customers_id.items())
        bots = list(self.data.bot_firms_id.items()) + list(self.data.bot_customers_id.items())

        non_bots = [(i, j) for i, j in all_agents if (i, j) not in bots]

        return non_bots

    def init(self):

        for i in range(self.n_customers):

            game_id = self.n_agents_to_wait

            self.n_agents_to_wait += 1

            customer_id = len(self.data.customers_id)

            if game_id not in self.data.customers_id.keys():

                self.data.customers_id[game_id] = customer_id
                self.data.bot_customers_id[game_id] = customer_id

                self.data.roles[game_id] = "customer"

        for i in range(self.n_firms):

            firm_id = len(self.data.firms_id)
            game_id = self.n_agents_to_wait

            self.n_agents_to_wait += 1

            if game_id not in self.data.firms_id.keys():

                self.data.firms_id[game_id] = firm_id
                self.data.bot_firms_id[game_id] = firm_id

                self.data.roles[game_id] = "firm"

        self.check_remaining_agents()

    def check_remaining_agents(self):

        remaining = len(self.data.roles) - (len(self.data.firms_id) + len(self.data.customers_id))

        if not remaining:
            self.data.current_state["init_done"] = True
            self.time_manager.check_state()

        else:
            self.log("Error: "
                    "Remaining agents to connect although all bots "
                    "and all real players seem to be connected.")

    # -------------------------------- customer ------------------------------------------- #
    def play_customer(self, customer_id):

        if self.time_manager.state == "active_has_played":
            extra_view, firm = self.customer_choice(customer_id)

            self.data.current_state["customer_extra_view_choices"][customer_id] = extra_view
            self.data.current_state["customer_firm_choices"][customer_id] = firm

            self.data.current_state["customer_replies"][customer_id] = 1

            self.time_manager.check_state()

    def customer_choice(self, customer_id):

        positions = self.data.current_state["firm_positions"]
        prices = self.data.current_state["firm_prices"]
        own_position = np.random.randint(self.n_positions)

        extra_view = self.customer_extra_view_choice()
        firm = self.customer_firm_choice(np.array([positions[0], positions[1]]),
                                         np.array([prices[0], prices[1]]),
                                         own_position)

        return extra_view, firm

    def customer_extra_view_choice(self):

        self.customer_attributes["extra_view_choice"] = \
            np.max(self.customer_attributes["extra_view_possibilities"])

        return self.customer_attributes["extra_view_choice"]

    def customer_firm_choice(self, positions, prices, own_position):

        field_of_view = [
            own_position - self.customer_attributes["extra_view_choice"],
            own_position + self.customer_attributes["extra_view_choice"]
        ]

        cond0 = positions >= field_of_view[0]
        cond1 = positions <= field_of_view[1]

        available_prices = prices[cond0 * cond1]

        firm_idx = np.arange(len(positions))
        available_firm = firm_idx[cond0 * cond1]

        if len(available_prices) == 1:
            self.customer_attributes["min_price"] = min(available_prices)
            firm_choice = np.random.choice(
                available_firm[np.where(available_prices == self.customer_attributes["min_price"])[0]]
            )

        elif len(available_prices) == 2:
            distance = [abs(own_position - pos) for pos in available_prices]
            firm_choice = np.argmin([i + j for i, j in zip(available_prices, distance)])

        else:
            self.customer_attributes["min_price"] = 0
            firm_choice = -1

        return firm_choice

    # ------------------------- Firm choice functions --------------------------------- #
    def play_active_firm(self, firm_id):

        if not self.data.current_state["active_replied"]:
            self.firm_active_choice_recording(firm_id)
        if self.time_manager.state == "active_has_played_and_all_customers_replied":
            self.firm_active_n_client(firm_id)

    def play_passive_firm(self):

        if self.time_manager.state == "active_has_played_and_all_customers_replied":
            self.data.current_state["passive_gets_results"] = True
            self.time_manager.check_state()

    def firm_active_choice_recording(self, firm_id):

        own_position = np.random.randint(1, self.n_positions)
        own_price = np.random.randint(1, self.firm_attributes["n_prices"])

        self.data.current_state["firm_positions"][firm_id] = own_position
        self.data.current_state["firm_prices"][firm_id] = own_price
        self.data.current_state["active_replied"] = True

        self.time_manager.check_state()

    def firm_active_n_client(self, firm_id):

        firm_choices = np.asarray(self.data.current_state["customer_firm_choices"])
        cond = firm_choices == firm_id
        n = sum(cond)

        price = self.data.current_state["firm_prices"][firm_id]

        self.data.current_state["firm_cumulative_profits"][firm_id] += n * price
        self.data.current_state["firm_profits"][firm_id] = n * price
        self.data.current_state["n_client"][firm_id] = n
        self.data.current_state["active_gets_results"] = True

        self.time_manager.check_state()

