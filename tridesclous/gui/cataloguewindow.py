import numpy as np

from .myqt import QT
import pyqtgraph as pg

from .cataloguecontroller import CatalogueController
from .traceviewer import CatalogueTraceViewer
from .peaklists import PeakList, ClusterPeakList
from .ndscatter import NDScatter
from .waveformviewer import WaveformViewer
from .similarity import SpikeSimilarityView, ClusterSimilarityView, ClusterRatioSimilarityView
from .pairlist import PairList
from .silhouette import Silhouette
from .waveformhistviewer import WaveformHistViewer
from .featuretimeviewer import FeatureTimeViewer

from .tools import ParamDialog, open_dialog_methods

from . import gui_params

from . import icons


import itertools
import datetime
import time

class CatalogueWindow(QT.QMainWindow):
    def __init__(self, catalogueconstructor):
        QT.QMainWindow.__init__(self)
        
        self.setWindowIcon(QT.QIcon(':/main_icon.png'))
        
        self.catalogueconstructor = catalogueconstructor
        self.controller = CatalogueController(catalogueconstructor=catalogueconstructor)
        
        self.traceviewer = CatalogueTraceViewer(controller=self.controller)
        self.peaklist = PeakList(controller=self.controller)
        self.clusterlist = ClusterPeakList(controller=self.controller)
        self.ndscatter = NDScatter(controller=self.controller)
        self.waveformviewer = WaveformViewer(controller=self.controller)
        self.spikesimilarityview = SpikeSimilarityView(controller=self.controller)
        self.clustersimilarityview = ClusterSimilarityView(controller=self.controller)
        self.clusterratiosimilarityview = ClusterRatioSimilarityView(controller=self.controller)
        self.pairlist = PairList(controller=self.controller)
        self.silhouette = Silhouette(controller=self.controller)
        self.waveformhistviewer = WaveformHistViewer(controller=self.controller)
        self.featuretimeviewer = FeatureTimeViewer(controller=self.controller)
        
        
        
        
        docks = {}

        docks['waveformviewer'] = QT.QDockWidget('waveformviewer',self)
        docks['waveformviewer'].setWidget(self.waveformviewer)
        #self.tabifyDockWidget(docks['ndscatter'], docks['waveformviewer'])
        self.addDockWidget(QT.Qt.RightDockWidgetArea, docks['waveformviewer'])
        

        docks['waveformhistviewer'] = QT.QDockWidget('waveformhistviewer',self)
        docks['waveformhistviewer'].setWidget(self.waveformhistviewer)
        self.tabifyDockWidget(docks['waveformviewer'], docks['waveformhistviewer'])

        docks['featuretimeviewer'] = QT.QDockWidget('featuretimeviewer',self)
        docks['featuretimeviewer'].setWidget(self.featuretimeviewer)
        self.tabifyDockWidget(docks['waveformhistviewer'], docks['featuretimeviewer'])
        
        
        docks['traceviewer'] = QT.QDockWidget('traceviewer',self)
        docks['traceviewer'].setWidget(self.traceviewer)
        #self.addDockWidget(QT.Qt.RightDockWidgetArea, docks['traceviewer'])
        self.tabifyDockWidget(docks['waveformviewer'], docks['traceviewer'])
        
        docks['peaklist'] = QT.QDockWidget('peaklist',self)
        docks['peaklist'].setWidget(self.peaklist)
        self.addDockWidget(QT.Qt.LeftDockWidgetArea, docks['peaklist'])
        
        docks['pairlist'] = QT.QDockWidget('pairlist',self)
        docks['pairlist'].setWidget(self.pairlist)
        self.splitDockWidget(docks['peaklist'], docks['pairlist'], QT.Qt.Horizontal)
        
        docks['clusterlist'] = QT.QDockWidget('clusterlist',self)
        docks['clusterlist'].setWidget(self.clusterlist)
        self.tabifyDockWidget(docks['pairlist'], docks['clusterlist'])
        
        #on bottom left
        docks['spikesimilarityview'] = QT.QDockWidget('spikesimilarityview',self)
        docks['spikesimilarityview'].setWidget(self.spikesimilarityview)
        self.addDockWidget(QT.Qt.LeftDockWidgetArea, docks['spikesimilarityview'])

        docks['clustersimilarityview'] = QT.QDockWidget('clustersimilarityview',self)
        docks['clustersimilarityview'].setWidget(self.clustersimilarityview)
        self.tabifyDockWidget(docks['spikesimilarityview'], docks['clustersimilarityview'])

        docks['clusterratiosimilarityview'] = QT.QDockWidget('clusterratiosimilarityview',self)
        docks['clusterratiosimilarityview'].setWidget(self.clusterratiosimilarityview)
        self.tabifyDockWidget(docks['spikesimilarityview'], docks['clusterratiosimilarityview'])
        

        docks['silhouette'] = QT.QDockWidget('silhouette',self)
        docks['silhouette'].setWidget(self.silhouette)
        self.tabifyDockWidget(docks['spikesimilarityview'], docks['silhouette'])
        
        
        docks['ndscatter'] = QT.QDockWidget('ndscatter',self)
        docks['ndscatter'].setWidget(self.ndscatter)
        self.tabifyDockWidget(docks['spikesimilarityview'], docks['ndscatter'])
        
        self.create_actions()
        self.create_toolbar()
        
        
    def create_actions(self):
        #~ self.act_save = QT.QAction(u'Save catalogue', self,checkable = False, icon=QT.QIcon.fromTheme("document-save"))
        self.act_save = QT.QAction(u'Save catalogue', self,checkable = False, icon=QT.QIcon(":/document-save.svg"))
        self.act_save.triggered.connect(self.save_catalogue)

        #~ self.act_refresh = QT.QAction(u'Refresh', self,checkable = False, icon=QT.QIcon.fromTheme("view-refresh"))
        self.act_refresh = QT.QAction(u'Refresh', self,checkable = False, icon=QT.QIcon(":/view-refresh.svg"))
        self.act_refresh.triggered.connect(self.refresh_with_reload)

        self.act_redetect_peak = QT.QAction(u'New peaks', self,checkable = False, icon=QT.QIcon(":/configure-shortcuts.svg"))
        self.act_redetect_peak.triggered.connect(self.redetect_peak)

        self.act_new_waveforms = QT.QAction(u'New waveforms', self,checkable = False, icon=QT.QIcon(":/configure-shortcuts.svg"))
        self.act_new_waveforms.triggered.connect(self.new_waveforms)

        self.act_new_noise_snippet = QT.QAction(u'New noise snippet', self,checkable = False, icon=QT.QIcon(":/configure-shortcuts.svg"))
        self.act_new_noise_snippet.triggered.connect(self.new_noise_snippet)

        self.act_new_features = QT.QAction(u'New features', self,checkable = False, icon=QT.QIcon(":/configure-shortcuts.svg"))
        self.act_new_features.triggered.connect(self.new_features)

        self.act_new_cluster = QT.QAction(u'New cluster', self,checkable = False, icon=QT.QIcon(":/configure-shortcuts.svg"))
        self.act_new_cluster.triggered.connect(self.new_cluster)

        self.act_compute_metrics = QT.QAction(u'Compute metrics', self,checkable = False, icon=QT.QIcon(":/configure-shortcuts.svg"))
        self.act_compute_metrics.triggered.connect(self.compute_metrics)


        #~ self.act_new_waveforms = QT.QAction(u'Yep', self,checkable = False, icon=QT.QIcon(":main_icon.png"))
        #~ self.act_new_waveforms.triggered.connect(self.new_waveforms)


    def create_toolbar(self):
        self.toolbar = QT.QToolBar('Tools')
        self.toolbar.setToolButtonStyle(QT.Qt.ToolButtonTextUnderIcon)
        self.addToolBar(QT.Qt.RightToolBarArea, self.toolbar)
        self.toolbar.setIconSize(QT.QSize(60, 40))
        
        self.toolbar.addAction(self.act_save)
        self.toolbar.addAction(self.act_refresh)
        #~ self.toolbar.addAction(self.act_setting)
        #TODO with correct settings (left and right)
        
        
        self.toolbar.addAction(self.act_redetect_peak)
        self.toolbar.addAction(self.act_new_waveforms)
        self.toolbar.addAction(self.act_new_noise_snippet)
        self.toolbar.addAction(self.act_new_features)
        self.toolbar.addAction(self.act_new_cluster)
        self.toolbar.addAction(self.act_compute_metrics)

    def save_catalogue(self):
        self.catalogueconstructor.save_catalogue()
    
    def refresh_with_reload(self):
        self.controller.reload_data()
        self.refresh()
    
    def refresh(self):
        #~ self.controller.reload_data()
        for w in self.controller.views:
            #TODO refresh only visible but need catch on visibility changed
            #~ print(w)
            w.refresh()
    
    def redetect_peak(self):
        dia = ParamDialog(gui_params.peak_detector_params)
        dia.resize(450, 500)
        if dia.exec_():
            d = dia.get()
            self.catalogueconstructor.re_detect_peak(**d)
            self.controller.init_plot_attributes()
        self.refresh()
    
    def new_waveforms(self):
        dia = ParamDialog(gui_params.waveforms_params)
        dia.resize(450, 500)
        if dia.exec_():
            d = dia.get()
            self.catalogueconstructor.extract_some_waveforms(**d)
        self.refresh()

    def new_noise_snippet(self):
        dia = ParamDialog(gui_params.noise_snippet_params)
        dia.resize(450, 500)
        if dia.exec_():
            d = dia.get()
            self.catalogueconstructor.extract_some_noise(**d)
            self.controller.check_plot_attributes()#this count noise
        self.refresh()

    def new_features(self):
        method, kargs = open_dialog_methods(gui_params.features_params_by_methods, self)
        if method is not None:
            self.catalogueconstructor.extract_some_features(method=method, **kargs)
            self.refresh()


    def new_cluster(self):
        method, kargs = open_dialog_methods(gui_params.cluster_params_by_methods, self)
        if method is not None:
            self.catalogueconstructor.find_clusters(method=method, **kargs)
            self.controller.on_new_cluster()
            self.refresh()
    
    def compute_metrics(self):
        dia = ParamDialog(gui_params.metrics_params)
        dia.resize(450, 500)
        if dia.exec_():
            d = dia.get()
            self.catalogueconstructor.compute_centroid()
            self.catalogueconstructor.compute_spike_waveforms_similarity(method=d['spike_waveforms_similarity'], size_max=d['size_max'])
            self.catalogueconstructor.compute_cluster_similarity(method=d['cluster_similarity'])
            self.catalogueconstructor.compute_cluster_ratio_similarity(method=d['cluster_ratio_similarity'])
            self.catalogueconstructor.compute_spike_silhouette(size_max=d['size_max'])
            #TODO refresh only metrics concerned
            self.refresh()
        
        
    

