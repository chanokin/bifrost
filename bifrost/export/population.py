from typing import Any, Dict, List
from bifrost.ir.layer import NeuronLayer, Layer
from bifrost.ir.input import InputLayer, SpiNNakerSPIFInput
from bifrost.ir.output import OutputLayer
from bifrost.ir.parameter import ParameterContext
from bifrost.ir.cell import (LIFCell, LICell, IFCell)
from bifrost.export.statement import Statement


def export_dict(d: Dict[Any, Any], join_str=",\n", n_spaces=0) -> Statement:
    def _export_dict_key(key: Any) -> str:
        if not isinstance(key, str):
            raise ValueError("Parameter key must be a string", key)
        return str(key)

    def _export_dict_value(value: Any) -> str:
        if isinstance(value, str):
            return f"'{str(value)}'"
        else:
            return str(value)

    pynn_dict = [f"{_export_dict_key(key)}={_export_dict_value(value)}"
                 for key, value in d.items()]
    spaces = " " * n_spaces
    return Statement((f"{join_str}{spaces}").join(pynn_dict), [])

def export_list(var: str, l: List[str], join_str=", ", n_spaces=0):
    spaces = " " * n_spaces
    lst = (f"{join_str}{spaces}").join([f"\"{v}\"" for v in l])

    return f"{var} = [{lst}]"

def export_cell_params(layer: Layer, context: ParameterContext[str],
                       join_str:str = ",\n", spaces:int = 8) -> Statement:
    # todo: take 'locations/addresses' from context and express as a function
    #       which returns a dictionary so that once it's called, we can use the
    #       ** operator to pass key-value pairs as parameters to cell class
    #       constructor
    cell_name = layer.cell.__class__.__name__
    sp = " " * spaces
    layer_name = str(layer)
    func_name = f"__map_func_{layer_name}"

    list_name = f"__parameter_names"
    dict_name = "__d"
    fcall = context.neuron_parameter(layer_name, 'p')
    names = export_list(list_name, context.parameter_names(layer.cell))
    params = []

    f = f"""
def {func_name}():
    {names}
    {dict_name} = dict()
    for p in {list_name}:
        k, v = {fcall}
        {dict_name}[k] = v
    return {dict_name}
    
    """
    print(f)
    return Statement(f"**({func_name}())", preambles=[f])

def export_layer(layer: Layer, context: ParameterContext[str]) -> Statement:
    if isinstance(layer, SpiNNakerSPIFInput):
        return export_layer_spif(layer, context)
    elif isinstance(layer, NeuronLayer):
        return export_layer_neuron(layer, context)
    elif isinstance(layer, InputLayer):
        pass
    elif isinstance(layer, OutputLayer):
        pass
    else:
        raise ValueError("Unknown layer type", layer)


def export_layer_neuron(layer: NeuronLayer, context: ParameterContext[str],
                        param_join_str=", ", pop_join_str=",\n") -> Statement:
    neuron = export_neuron_type(layer, context, join_str=", ", spaces=0)
    structure = export_structure(layer)
    param_template = param_join_str.join([
            f"{layer.size}", f"{neuron.value}", f"structure={structure.value}",
            "label='{}'"])

    statement = Statement()
    for channel in range(layer.channels):
        var = f"{layer.variable(channel)}"
        par = param_template.format(var)
        statement += Statement(f"{var} = p.Population({par})",
                               imports=neuron.imports,)

    if isinstance(statement.imports, tuple):
        statement.imports = structure.imports

    return statement


def export_layer_input(layer: InputLayer) -> Statement:
    if isinstance(layer.source, SpiNNakerSPIFInput):
        spif_layer = layer.source
        return Statement(
            [
                f"""{layer.variable(channel)} = p.Population(None,p.external_devices.SPIFRetinaDevice(\
base_key={channel},width={spif_layer.x},height={spif_layer.y},sub_width={spif_layer.x_sub},sub_height={spif_layer.y_sub},\
input_x_shift={spif_layer.x_shift},input_y_shift={spif_layer.y_shift}))"""
                for channel in range(layer.channels)
            ]
        )
    else:
        raise ValueError("Unknown input source", layer.source)

def export_neuron_type(layer: NeuronLayer, ctx: ParameterContext[str],
                       join_str:str = ",\n", spaces:int = 0) -> Statement:
    pynn_parameter_statement = export_cell_params(layer, ctx, join_str, spaces)
    cell_type = get_pynn_cell_type(layer.cell, layer.synapse)
    return Statement(
        f"p.{cell_type}({pynn_parameter_statement.value})",
        pynn_parameter_statement.imports,
    )

def export_structure(layer):
    ratio = float(layer.shape[1]) / layer.shape[0]
    return Statement(f"Grid2D({ratio})",
                     imports=['from pyNN.space import Grid2D'])

# todo: this is PyNN, I guess we should move it somewhere else
def get_pynn_cell_type(cell, synapse):
    if isinstance(cell, (LICell, LIFCell)):
        cell_type = 'IF'  # in PyNN this is missing the L for some #$%@ reason
    elif isinstance(cell, IFCell):
        cell_type = 'NIF' #  as in Non-leaky Integrate and Fire
    else:
        raise NotImplementedError("Neuron type not yet available")

    if synapse.synapse_type == 'current':
        syn_type = 'curr'
    elif synapse.synapse_type == 'conductance':
        syn_type = 'cond'
    else:
        raise NotImplementedError(
                f"Synapse type not yet available {synapse.synapse_type}")

    if synapse.synapse_shape == 'exponential':
        syn_shape = 'exp'
    elif synapse.synapse_shape == 'alpha':
        syn_shape = 'alpha'
    elif synapse.synapse_shape == 'delta':
        syn_shape = 'delta'
    else:
        raise NotImplementedError(
                f"Synapse 'shape' not yet available {synapse.synapse_shape}")

    return "{}_{}_{}".format(cell_type, syn_type, syn_shape)




# def output_ethernet(layer: )
