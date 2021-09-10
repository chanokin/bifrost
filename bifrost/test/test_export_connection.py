from bifrost.export.torch import TorchContext
from bifrost.ir.connection import *
from bifrost.export.connection import *
from bifrost.export.pynn import SIM_NAME
from bifrost.parse.remove_blank import remove_blank as rb

class MockContext(ParameterContext):
    def weights(self, layer: str, channel: int) -> str:
        return "some_weights" + str(channel)

torch_context = TorchContext({"layer.weights": "lw"})

# def test_conv2d_connection_to_pynn():
#     k2 = torch.tensor([[1, 2], [3, 4]])
#     cc = ConvolutionConnector(k2)
#     c = MockContext()
#     assert (
#         export_connector(cc, "x", c)[0].value
#         == "p.ConvolutionConnector([[1,2],[3,4]],padding=[1,1])"
#     )
#     assert len(export_connector(cc, "x", c)[0].imports) == 0
#     assert export_connector(cc, "x", c)[1] is None

# weights are specified in torch way, need to add test for ml_genn
def test_matrix_connection_to_pynn():
    l1 = NeuronLayer("x", 1, 1)
    l2 = NeuronLayer("y", 1, 1)
    torch_context = TorchContext({"l_x_1_1": "0", "l_y_1_1": "lw"})
    c = Connection(l1, l2, MatrixConnector("layer.weights"))
    var = 'c_x_0__to__y_0'
    actual = export_connection(c, torch_context, join_str=", ", spaces=0)
    # projections end in a line break
    expected = f"{var} = {SIM_NAME}.Projection(l_x_1_[0], l_y_1_[0], " \
               f"{SIM_NAME}.AllToAllConnector(), {SIM_NAME}.StaticSynapse())" \
               f"{var}.set(weight=_params[\"layer.weights.weight\"][0, 0])"
    assert rb(str(actual)) == rb(expected)
    assert len(actual.imports) == 0
