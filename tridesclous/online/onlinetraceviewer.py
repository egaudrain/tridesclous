import numpy as np
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg


import pyacq
from pyacq import WidgetNode,ThreadPollInput, StreamConverter, InputStream
from pyacq.viewers import QOscilloscope

#~ _dtype_spike = [('index', 'int64'), ('label', 'int64'), ('jitter', 'float64'),]
from ..peeler import _dtype_spike


class OnlineTraceViewer(QOscilloscope):
    
    _input_specs = {'signals': dict(streamtype='signals'),
                                'spikes': dict(streamtype='events', shape = (-1, ),  dtype=_dtype_spike),
                                    }
    
    _default_params = QOscilloscope._default_params

    
    def __init__(self, **kargs):
        QOscilloscope.__init__(self, **kargs)

    def _configure(self, peak_buffer_size = 10000, catalogue=None, **kargs):
        QOscilloscope._configure(self, **kargs)
        self.peak_buffer_size = peak_buffer_size
        self.catalogue = catalogue
        assert catalogue is not None
    
    def _initialize(self, **kargs):
        QOscilloscope._initialize(self, **kargs)
        
        self.inputs['spikes'].set_buffer(size=self.peak_buffer_size, double=False)
        
        # poller onpeak
        self._last_peak = 0
        self.poller_peak = ThreadPollInput(input_stream=self.inputs['spikes'], return_data=True)
        self.poller_peak.new_data.connect(self._on_new_peak)
        
        self.spikes_array = self.inputs['spikes'].buffer.buffer
        
        self._default_color = QtGui.QColor('#FFFFFF')#TODO
        self.scatters = {}
        for k in self.catalogue['cluster_labels']:
            color = self.catalogue['cluster_colors'].get(k, (1,1,1))
            r, g, b = color
            qcolor = QtGui.QColor(r*255, g*255, b*255)
            qcolor.setAlpha(150)
            scatter = pg.ScatterPlotItem(x=[ ], y= [ ], pen=None, brush=qcolor, size=10, pxMode = True)
            self.scatters[k] = scatter
            self.plot.addItem(scatter)

        #~ for i in range(self.nb_channel):
            #~ color = self._default_color
            #~ color.setAlpha(150)
            #~ scatter = pg.ScatterPlotItem(x=[ ], y= [ ], pen=None, brush=color, size=10, pxMode = True)
            #~ self.scatters.append(scatter)
            #~ self.plot.addItem(scatter)
        

    def _start(self, **kargs):
        QOscilloscope._start(self, **kargs)
        self._last_peak = 0
        self.poller_peak.start()

    def _stop(self, **kargs):
        QOscilloscope._stop(self, **kargs)
        self.poller_peak.stop()
        self.poller_peak.wait()

    def _close(self, **kargs):
        QOscilloscope._close(self, **kargs)
    
    def reset_curves_data(self):
        QOscilloscope.reset_curves_data(self)
        self.t_vect_full = np.arange(0,self.full_size, dtype=float)/self.sample_rate
        self.t_vect_full -= self.t_vect_full[-1]
    
    def _on_new_peak(self, pos, data):
        self._last_peak = pos
    
    def autoestimate_scales(self):
        # in our case preprocesssed signal is supposed to be normalized
        self.all_mean = np.zeros(self.nb_channel,)
        self.all_sd = np.ones(self.nb_channel,)
        return self.all_mean, self.all_sd

    
    def _refresh(self, **kargs):
        QOscilloscope._refresh(self, **kargs)
        
        mode = self.params['mode']
        gains = np.array([p['gain'] for p in self.by_channel_params.children()])
        offsets = np.array([p['offset'] for p in self.by_channel_params.children()])
        visibles = np.array([p['visible'] for p in self.by_channel_params.children()], dtype=bool)
        
        head = self._head
        full_arr = self.inputs['signals'].get_data(head-self.full_size, head)
        if self._last_peak==0:
            return

        keep = (self.spikes_array['index']>head - self.full_size) & (self.spikes_array['index']<head)
        spikes = self.spikes_array[keep]
        
        #~ spikes = self.spikes_array['index'][keep]
        
        spikes_ind = spikes['index'] - (head - self.full_size)
        spikes_amplitude = full_arr[spikes_ind, :]
        spikes_amplitude[:, visibles] *= gains[visibles]
        spikes_amplitude[:, visibles] += offsets[visibles]
        
        if mode=='scroll':
            peak_times = self.t_vect_full[spikes_ind]
        elif mode =='scan':
            #some trick to play with fake time
            front = head % self.full_size
            ind1 = (spikes['index']%self.full_size)<front
            ind2 = (spikes['index']%self.full_size)>front
            peak_times = self.t_vect_full[spikes_ind]
            peak_times[ind1] += (self.t_vect_full[front] - self.t_vect_full[-1])
            peak_times[ind2] += (self.t_vect_full[front] - self.t_vect_full[0])
        
        for i, k in enumerate(self.catalogue['cluster_labels']):
            keep = k==spikes['label']
            if np.sum(keep)>0:
                chan = self.catalogue['max_on_channel'][i]
                if visibles[chan]:
                    self.scatters[k].setData(peak_times[keep], spikes_amplitude[keep, chan])
                else:
                    self.scatters[k].setData([], [])
            else:
                self.scatters[k].setData([], [])
        
