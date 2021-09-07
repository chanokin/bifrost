from bifrost.export.torch import TorchContext
from bifrost.ir.output import OutputLayer
from bifrost.ir.input import InputLayer
from bifrost.ir.connection import (
    AllToAllConnector, Connection, MatrixConnector, ConvolutionConnector,
    DenseConnector, PoolingConnector, Connector
)
from bifrost.ir.cell import LIFCell, LICell
from bifrost.ir.layer import NeuronLayer, Layer
from bifrost.ir.synapse import Synapse, ConvolutionSynapse, DenseSynapse
from typing import Callable, List, Optional, Tuple
from bifrost.ir.parameter import ParameterContext
from bifrost.ir.network import Network
from collections import OrderedDict
from typing import Dict

import numpy as np

import os
os.environ["CUDA_VISIBLE_DEVICES"]=""

import torch
torch.device("cpu")

import pytorch_lightning as pl
from torchinfo import summary
from torchinfo.layer_info import LayerInfo
import norse.torch as norse

# todo: remove all the magic constants and move them to a common file

Continuation = Callable[[Network], Network]

def module_to_list(model: torch.nn.Module, data_shape: tuple):
    s = summary(model, data_shape, verbose=0)

    ld = OrderedDict({i: l
                      for i, l in enumerate(s.summary_list)
                      if not (isinstance(l.module, torch.nn.BatchNorm2d) or
                              isinstance(l.module, norse.SequentialState) or
                              i == 0)})

    return ld

def torch_to_network(
    model: torch.nn.Module, input_layer: InputLayer, output_layer: OutputLayer
) -> Network:
    if not isinstance(model, (norse.SequentialState, pl.LightningModule)):
            raise ValueError("Unknown model type", type(model))

    # Batch, Channels, Width, Height
    # this has to be in (8, 3, 28, 28) BCXY format
    input_shape = (1, input_layer.channels, *input_layer.source.shape)
    net_dict = module_to_list(model, input_shape)

    default_network = Network(layers=[input_layer], connections=[])

    network = module_to_ir(modules=net_dict, network=default_network)

    if output_layer is not None:
        layers = network.layers + [output_layer]
        out_conn = [Connection(pre=network.layers[-1], post=output_layer,
                               connector=MatrixConnector("0"))]
        conns = network.connections + out_conn
        network = Network(layers=layers, connections=conns)

    return network


def torch_to_context(net: Network, modules: List[torch.nn.Module]) -> ParameterContext[str]:
    input_layer = net.layers[0] # assuming the first layer is of input type
    input_shape = (1, input_layer.channels, *input_layer.source.shape)
    net_dict = module_to_list(modules, input_shape)

    for k in net_dict:
        module = net_dict[k].module
        if hasattr(module, 'weight'):
            print(k, module.weight.detach().numpy())
            net_dict[k]['weight'] = module.weight.detach().numpy()

        if hasattr(module, 'p'):  # parameters for LI or LIF neurons
            params = module.p
            for name, val in zip(params._fields, params):
                print(k, name, val)
                net_dict[k][name] = val.detach().numpy()



    layer_map = {
        str(l): l.name
        for l in net.layers
        if not (isinstance(l, InputLayer))
    }

    return TorchContext(layer_map), net_dict


def module_to_ir(
    modules: Dict[int, LayerInfo],
    network: Network,
) -> Network:

    layer_map = {}
    layers = network.layers
    connections = network.connections
    keys = list(modules.keys())
    last_neuron_idx = - 1
    for idx, k in enumerate(keys):
        layer_info = modules[k]
        name = layer_info.class_name.lower()
        if name in ['conv2d', 'avgpool2d']:
            continue

        if name in ['licell', 'lifcell']:
            size = int(np.prod(layer_info.output_size[-2:]))
            channels = layer_info.output_size[1]
            cell = __choose_cell(layer_info)

            connector = __get_connector(last_neuron_idx + 1, idx, keys, modules)
            synapse = __get_synapse(last_neuron_idx + 1, idx, keys, modules)
            post = NeuronLayer(f"{name}_{k}", size, channels, cell=cell,
                               synapse=synapse)
            conn = Connection(layers[-1], post, connector)

            layers.append(post)
            connections.append(conn)

            last_neuron_idx = idx
            continue

        # this should not be reached
        raise ValueError("Unknown torch module ", name)

    return network


def __choose_cell(layer_info:LayerInfo):
    name = layer_info.class_name
    if 'licell' in name:
        return LICell()
    else:
        return LIFCell()  # default


def __choose_synapse_shape(torch_params):
    if hasattr(torch_params, 'alpha'):
        return 'alpha'
    else:
        return 'exponential'

def __get_synapse(start_idx: int, end_idx: int, keys: List[int],
                    modules: Dict[int, LayerInfo]) -> Synapse:
    syn = None
    for conn_idx in range(start_idx, end_idx):
        k = keys[conn_idx]
        name = modules[k].class_name.lower()
        if name in 'conv2d':
            syn = ConvolutionSynapse()
            continue
        elif name in 'dense':
            syn = DenseSynapse()
            continue
        elif name in 'linear':
            syn = StaticSynapse()
        elif name in 'avgpool2d':
            continue
        # this should not be reached
        raise ValueError("Unknown connector", name)

    layer_info = modules[keys[end_idx]]
    syn.synapse_shape = __choose_synapse_shape(layer_info.module.p)
    # note: seems we only support current synapse types as of now (7/9/21)
    return syn


def __get_connector(start_idx: int, end_idx: int, keys: List[int],
                    modules: Dict[int, LayerInfo]) -> Connector:
    pool_idx = None
    ctor = None
    for conn_idx in range(start_idx, end_idx):
        k = keys[conn_idx]
        name = modules[k].class_name.lower()
        if name in 'conv2d':
            ctor = ConvolutionConnector(str(k), pooling_key=str(pool_idx))
            continue
        elif name in 'dense':
            ctor = DenseConnector(str(k), pooling_key=str(pool_idx))
            continue
        elif name in 'linear':
            ctor = MatrixConnector(str(k))

        elif name in 'avgpool2d':
            pool_idx = k
            continue
        # this should not be reached
        raise ValueError("Unknown connector", name)

    return ctor


def module_to_layer(
    module: torch.nn.Module, index: int, input_channels: int, input_neurons: int
) -> Layer:
    if isinstance(module, norse.LICell):
        return NeuronLayer(str(index), input_neurons, input_channels,
                           index=index, cell=LICell())
    elif isinstance(module, norse.LIFCell):
        return NeuronLayer(str(index), input_neurons, input_channels, index=index,
                           cell=LIFCell())
    else:
        raise ValueError("Unknown torch module layer", module)
