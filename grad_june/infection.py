import torch
from torch_geometric.data import HeteroData
from torch.distributions.utils import probs_to_logits

from grad_june.demographics import get_people_per_area


class Bernoulli(torch.autograd.Function):
    generate_vmap_rule = True

    @staticmethod
    def forward(p):
        result = torch.bernoulli(p)
        return result

    @staticmethod
    def backward(ctx, grad_output):
        result = ctx.result
        p = ctx.p
        w_minus = 1.0 / p
        w_plus = 1.0 / (1.0 - p)
        ws = torch.where(result == 1, w_minus, w_plus) / 2
        return grad_output * ws
        #return grad_output * torch.ones_like(p)

    @staticmethod
    def setup_context(ctx, inputs, output):
        result = output
        ctx.result = result
        ctx.p = inputs[0]

    @staticmethod
    def jvp(ctx, gI):
        result = ctx.result
        p = ctx.p
        w_minus = 1.0 / p
        w_plus = 1.0 / (1.0 - p)
        ws = torch.where(result == 1, w_minus, w_plus) / 2
        return gI * ws
        return gI * torch.ones_like(p)

class STBernoulli(torch.autograd.Function):
    generate_vmap_rule = True

    @staticmethod
    def forward(p):
        result = torch.bernoulli(p)
        return result

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output 

    @staticmethod
    def setup_context(ctx, inputs, output):
        pass



class IsInfectedSampler(torch.nn.Module):
    def forward(self, not_infected_probs):
        """
        Here we need to sample the infection status of each agent and the variant that
        the agent gets in case of infection.
        To do this, we construct a tensor of size [M+1, N], where M is the number of
        variants and N the number of agents. The extra dimension in M will represent
        the agent not getting infected, so that it can be sampled as an outcome using
        the Gumbel-Softmax reparametrization of the categorical distribution.
        """
        probs = 1.0 - not_infected_probs
        return STBernoulli.apply(probs)
        #logits = probs_to_logits(
        #    torch.vstack((not_infected_probs, 1.0 - not_infected_probs))
        #)
        logits = torch.log(
            torch.vstack((not_infected_probs, 1.0 - not_infected_probs))
        )
        infection = torch.nn.functional.gumbel_softmax(
            logits, dim=0, tau=0.1, hard=True
        )
        is_infected = 1.0 - infection[0, :]
        return is_infected


def infect_people(data: HeteroData, time: int, new_infected: torch.Tensor):
    """
    Sets the `new_infected` individuals to infected at time `time`.

    **Arguments:**

    - `data`: the graph data
    - `time`: the time step at which the infection happens
    - `new_infected`: a tensor of size [N] where N is the number of agents.
    """
    data["agent"].susceptibility = torch.clamp(
        data["agent"].susceptibility - new_infected, min=0.0
    )
    data["agent"].is_infected = data["agent"].is_infected + new_infected
    data["agent"].infection_time = data["agent"].infection_time + new_infected * (
        time - data["agent"].infection_time
    )