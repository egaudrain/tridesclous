from tridesclous import *
import  pyqtgraph as pg
from matplotlib import pyplot



def get_controller():
    dataio = DataIO(dirname='test_peeler')
    catalogueconstructor = CatalogueConstructor(dataio=dataio)
    initial_catalogue = dataio.load_catalogue()
    controller = PeelerController(dataio=dataio,catalogue=initial_catalogue)
    return controller


def test_Peelercontroller():
    controller = get_controller()
    assert controller.cluster_labels is not None
    

def test_PeelerTraceViewer():
    controller = get_controller()
    
    app = pg.mkQApp()
    traceviewer = PeelerTraceViewer(controller=controller)
    traceviewer.show()
    traceviewer.resize(800,600)
    app.exec_()


def test_SpikeList():
    controller = get_controller()
    
    app = pg.mkQApp()
    traceviewer = SpikeList(controller)
    traceviewer.show()
    traceviewer.resize(800,600)
    app.exec_()

def test_ClusterSpikeList():
    controller = get_controller()
    
    app = pg.mkQApp()
    traceviewer = ClusterSpikeList(controller)
    traceviewer.show()
    traceviewer.resize(800,600)
    app.exec_()






def test_PeelerWindow():
    dataio = DataIO(dirname='test_peeler')
    initial_catalogue = dataio.load_catalogue(chan_grp=0)

    app = pg.mkQApp()
    win = PeelerWindow(dataio=dataio, catalogue=initial_catalogue)
    win.show()
    app.exec_()

    
    
if __name__ == '__main__':
    #~ test_Peelercontroller()
    
    #~ test_PeelerTraceViewer()
    #~ test_SpikeList()
    #~ test_ClusterSpikeList()
    
    test_PeelerWindow()


