import os
import json
from collections import OrderedDict
import time
import pickle
import itertools

import numpy as np
import scipy.signal
import scipy.interpolate
import seaborn as sns
sns.set_style("white")

import sklearn

from . import signalpreprocessor
from . import  peakdetector
from . import decomposition
from . import cluster 
from . import metrics

from .tools import median_mad, get_pairs_over_threshold


from .iotools import ArrayCollection

import matplotlib.pyplot as plt

from . import labelcodes



_persistent_metrics = ('spike_waveforms_similarity', 'cluster_similarity',
                        'cluster_ratio_similarity', 'spike_silhouette')

_reset_after_peak_arrays = ('some_peaks_index', 'some_waveforms', 'some_features',
                        'channel_to_features', 
                        'some_noise_index', 'some_noise_snippet', 'some_noise_features',
                        ) + _persistent_metrics

_persitent_arrays = ('all_peaks', 'signals_medians','signals_mads', 'clusters') + _reset_after_peak_arrays



_dtype_peak = [('index', 'int64'), ('label', 'int64'), ('segment', 'int64'),]

_dtype_cluster = [('cluster_label', 'int64'), ('cell_label', 'int64'), 
            ('max_on_channel', 'int64'), ('max_peak_amplitude', 'float64'),
            ('waveform_rms', 'float64'), ('nb_peak', 'int64'),]


class CatalogueConstructor:
    """
    CatalogueConstructor scan a smal part of the dataset to construct the catalogue.
    
    
    
    """
    def __init__(self, dataio, chan_grp=None, name='catalogue_constructor'):
        self.dataio = dataio
        
        if chan_grp is None:
            chan_grp = min(self.dataio.channel_groups.keys())
        self.chan_grp = chan_grp
        self.nb_channel = self.dataio.nb_channel(chan_grp=self.chan_grp)
        self.geometry = self.dataio.get_geometry(chan_grp=self.chan_grp)
        
        self.catalogue_path = os.path.join(self.dataio.channel_group_path[chan_grp], name)
        
        if not os.path.exists(self.catalogue_path):
            os.mkdir(self.catalogue_path)
        
        self.arrays = ArrayCollection(parent=self, dirname=self.catalogue_path)
        
        self.info_filename = os.path.join(self.catalogue_path, 'info.json')
        if not os.path.exists(self.info_filename):
            #first init
            self.info = {}
            self.flush_info()
        else:
            with open(self.info_filename, 'r', encoding='utf8') as f:
                self.info = json.load(f)
        
        
        for name in _persitent_arrays:
            # this set attribute to class if exsits
            self.arrays.load_if_exists(name)
            
        if self.all_peaks is not None:
            self.memory_mode='memmap'
        
        
        
        self.projector = None
    
    def flush_info(self):
        with open(self.info_filename, 'w', encoding='utf8') as f:
            json.dump(self.info, f, indent=4)
    
    def __repr__(self):
        t = "CatalogueConstructor <id: {}> \n  workdir: {}\n".format(id(self), self.catalogue_path)
        if self.all_peaks is None:
            t += '  Signal pre-processing not done yet'
            return t
        
        t += "  nb_peak: {}\n".format(self.nb_peak)
        nb_peak_by_segment = [ np.sum(self.all_peaks['segment']==i)  for i in range(self.dataio.nb_segment)]
        t += '  nb_peak_by_segment: '+', '.join('{}'.format(n) for n in nb_peak_by_segment)+'\n'

        if self.some_waveforms is not None:
            t += '  n_left {} n_right {}\n'.format(self.info['params_waveformextractor']['n_left'],
                                                self.info['params_waveformextractor']['n_right'])
            t += '  some_waveforms.shape: {}\n'.format(self.some_waveforms.shape)
            
        if self.some_features is not None:
            t += '  some_features.shape: {}\n'.format(self.some_features.shape)
        
        if hasattr(self, 'cluster_labels'):
            t += '  cluster_labels {}\n'.format(self.cluster_labels)
        
        
        return t

    @property
    def nb_peak(self):
        if self.all_peaks is None:
            return 0
        return self.all_peaks.size

    @property
    def cluster_labels(self):
        if self.clusters is not None:
            return self.clusters['cluster_label']
        else:
            return np.array([], dtype='int64')
    
    @property
    def positive_cluster_labels(self):
        return self.cluster_labels[self.cluster_labels>=0] 

    
    def reload_data(self):
        if not hasattr(self, 'memory_mode') or not self.memory_mode=='memmap':
            return
        
        for name in _persitent_arrays:
            # this set attribute to class if exsits
            self.arrays.load_if_exists(name)
    
    def set_preprocessor_params(self, chunksize=1024,
            memory_mode='memmap',
            
            internal_dtype = 'float32',
            
            #signal preprocessor
            signalpreprocessor_engine='numpy',
            highpass_freq=300., 
            lowpass_freq=None,
            smooth_size=0,
            common_ref_removal=False,
            
            lostfront_chunksize=128,
            
            
            #peak detector
            peakdetector_engine='numpy',
            peak_sign='-', relative_threshold=7, peak_span=0.0002,
            
            ):
        
        #TODO remove stuff if already computed
        
        
        self.chunksize = chunksize
        self.memory_mode = memory_mode
        
        #~ for name, dtype in [('peak_pos', 'int64'),
                                        #~ ('peak_segment', 'int64'),
                                        #~ ('peak_label', 'int32')]:
            #~ self.arrays.initialize_array(name, self.memory_mode,  dtype, (-1, ))
        self.arrays.initialize_array('all_peaks', self.memory_mode,  _dtype_peak, (-1, ))
        
        
        self.params_signalpreprocessor = dict(highpass_freq=highpass_freq, lowpass_freq=lowpass_freq, 
                        smooth_size=smooth_size, common_ref_removal=common_ref_removal,
                        lostfront_chunksize=lostfront_chunksize, output_dtype=internal_dtype)
        SignalPreprocessor_class = signalpreprocessor.signalpreprocessor_engines[signalpreprocessor_engine]
        self.signalpreprocessor = SignalPreprocessor_class(self.dataio.sample_rate, self.nb_channel, chunksize, self.dataio.source_dtype)
        
        
        self.params_peakdetector = dict(peak_sign=peak_sign, relative_threshold=relative_threshold, peak_span=peak_span)
        PeakDetector_class = peakdetector.peakdetector_engines[peakdetector_engine]
        self.peakdetector = PeakDetector_class(self.dataio.sample_rate, self.nb_channel,
                                                        self.chunksize, internal_dtype)
        
        #TODO make processed data as int32 ???
        for i in range(self.dataio.nb_segment):
            self.dataio.reset_processed_signals(seg_num=i, chan_grp=self.chan_grp, dtype=internal_dtype)
        
        #~ self.nb_peak = 0
        
        #TODO put all params in info
        self.info['internal_dtype'] = internal_dtype
        self.info['chunksize'] = chunksize
        self.info['params_signalpreprocessor'] = self.params_signalpreprocessor
        self.info['params_peakdetector'] = self.params_peakdetector
        self.flush_info()
    
    
    def estimate_signals_noise(self, seg_num=0, duration=10.):
        
        length = int(duration*self.dataio.sample_rate)
        length -= length%self.chunksize
        
        assert length<self.dataio.get_segment_length(seg_num), 'duration exeed size'
        
        name = 'filetered_sigs_for_noise_estimation_seg_{}'.format(seg_num)
        shape=(length - self.params_signalpreprocessor['lostfront_chunksize'], self.nb_channel)
        filtered_sigs = self.arrays.create_array(name, self.info['internal_dtype'], shape, 'memmap')
        
        params2 = dict(self.params_signalpreprocessor)
        params2['normalize'] = False
        self.signalpreprocessor.change_params(**params2)
        
        iterator = self.dataio.iter_over_chunk(seg_num=seg_num, chan_grp=self.chan_grp, chunksize=self.chunksize, i_stop=length,
                                                    signal_type='initial',  return_type='raw_numpy')
        for pos, sigs_chunk in iterator:
            pos2, preprocessed_chunk = self.signalpreprocessor.process_data(pos, sigs_chunk)
            if preprocessed_chunk is not None:
                filtered_sigs[pos2-preprocessed_chunk.shape[0]:pos2, :] = preprocessed_chunk

        #create  persistant arrays
        self.arrays.create_array('signals_medians', self.info['internal_dtype'], (self.nb_channel,), 'memmap')
        self.arrays.create_array('signals_mads', self.info['internal_dtype'], (self.nb_channel,), 'memmap')
        
        self.signals_medians[:] = signals_medians = np.median(filtered_sigs[:pos2], axis=0)
        self.signals_mads[:] = np.median(np.abs(filtered_sigs[:pos2]-signals_medians),axis=0)*1.4826
        
        #detach filetered signals even if the file remains.
        self.arrays.detach_array(name)
        

    def signalprocessor_one_chunk(self, pos, sigs_chunk, seg_num, detect_peak=True):

        pos2, preprocessed_chunk = self.signalpreprocessor.process_data(pos, sigs_chunk)
        if preprocessed_chunk is  None:
            return
        
        self.dataio.set_signals_chunk(preprocessed_chunk, seg_num=seg_num, chan_grp=self.chan_grp,
                        i_start=pos2-preprocessed_chunk.shape[0], i_stop=pos2, signal_type='processed')
        
        if detect_peak:
            n_peaks, chunk_peaks = self.peakdetector.process_data(pos2, preprocessed_chunk)
            
            if chunk_peaks is not None:
                peaks = np.zeros(chunk_peaks.size, dtype=_dtype_peak)
                peaks['index'] = chunk_peaks
                peaks['segment'][:] = seg_num
                peaks['label'][:] = labelcodes.LABEL_UNCLASSIFIED
                self.arrays.append_chunk('all_peaks',  peaks)
    
    
    def run_signalprocessor_loop_one_segment(self, seg_num=0, duration=60., detect_peak=True):
        

        
        length = int(duration*self.dataio.sample_rate)
        length = min(length, self.dataio.get_segment_length(seg_num))
        length -= length%self.chunksize

        #TODO make this by segment
        self.info['processed_length'] = length
        self.flush_info()
        
        #initialize engines
        
        p = dict(self.params_signalpreprocessor)
        p['normalize'] = True
        p['signals_medians'] = self.signals_medians
        p['signals_mads'] = self.signals_mads
        self.signalpreprocessor.change_params(**p)
        
        self.peakdetector.change_params(**self.params_peakdetector)
        
        iterator = self.dataio.iter_over_chunk(seg_num=seg_num, chan_grp=self.chan_grp, chunksize=self.chunksize, i_stop=length,
                                                    signal_type='initial', return_type='raw_numpy')
        for pos, sigs_chunk in iterator:
            #~ print(seg_num, pos, sigs_chunk.shape)
            self.signalprocessor_one_chunk(pos, sigs_chunk, seg_num, detect_peak=detect_peak)
    
    
    def finalize_signalprocessor_loop(self):
        self.dataio.flush_processed_signals(seg_num=0, chan_grp=self.chan_grp)
        
        #~ self.arrays.finalize_array('peak_pos')
        #~ self.arrays.finalize_array('peak_label')
        #~ self.arrays.finalize_array('peak_segment')
        
        self.arrays.finalize_array('all_peaks')
        self._reset_waveform_and_features()
        self.on_new_cluster()
    
    def run_signalprocessor(self, duration=60., detect_peak=True):
        for seg_num in range(self.dataio.nb_segment):
            self.run_signalprocessor_loop_one_segment(seg_num=seg_num, duration=duration, detect_peak=detect_peak)
        self.finalize_signalprocessor_loop()
    
    def re_detect_peak(self, peakdetector_engine='numpy', peak_sign='-', relative_threshold=7, peak_span=0.0002):
        
        #TODO if not peak detector in class
        self.params_peakdetector = dict(peak_sign=peak_sign, relative_threshold=relative_threshold, peak_span=peak_span)
        PeakDetector_class = peakdetector.peakdetector_engines[peakdetector_engine]
        self.peakdetector = PeakDetector_class(self.dataio.sample_rate, self.nb_channel,
                                                        self.info['chunksize'], self.info['internal_dtype'])

        self.peakdetector.change_params(**self.params_peakdetector)
        
        self.info['params_peakdetector'] = self.params_peakdetector
        self.flush_info()
        
        self.arrays.initialize_array('all_peaks', self.memory_mode,  _dtype_peak, (-1, ))
        
        #TODO clip i_stop with duration ???
        
        for seg_num in range(self.dataio.nb_segment):
            
            self.peakdetector.change_params(**self.params_peakdetector)#this reset the fifo index
            
            iterator = self.dataio.iter_over_chunk(seg_num=seg_num, chan_grp=self.chan_grp,
                            chunksize=self.info['chunksize'], i_stop=None, signal_type='processed', return_type='raw_numpy')
            for pos, preprocessed_chunk in iterator:
                n_peaks, chunk_peaks = self.peakdetector.process_data(pos, preprocessed_chunk)
            
                if chunk_peaks is not None:
                    peaks = np.zeros(chunk_peaks.size, dtype=_dtype_peak)
                    peaks['index'] = chunk_peaks
                    peaks['segment'][:] = seg_num
                    peaks['label'][:] = labelcodes.LABEL_UNCLASSIFIED
                    self.arrays.append_chunk('all_peaks',  peaks)

        self.arrays.finalize_array('all_peaks')
        self._reset_waveform_and_features()
        self.on_new_cluster()
    
    def _reset_waveform_and_features(self):
        """Must be called after peak detection
        """
        #TODO fix this need to delete really this arrays but size=0 is buggy
        
        #~ self.arrays.create_array('some_peaks_index', 'int64', (0,), self.memory_mode)
        #~ self.arrays.create_array('some_waveforms', self.info['internal_dtype'], (0,0,0), self.memory_mode)
        #~ self.arrays.create_array('some_features', self.info['internal_dtype'], (0,0), self.memory_mode)
        
        for name in _reset_after_peak_arrays:
            self.arrays.detach_array(name)
            setattr(self, name, None)
    
    def extract_some_waveforms(self, n_left=None, n_right=None, index=None, 
                                    mode='rand', nb_max=10000,
                                    align_waveform=False, subsample_ratio=20):
        """
        
        """
        if n_left is None or n_right is None:
            assert  'params_waveformextractor' in self.info
            n_left = self.info['params_waveformextractor']['n_left']
            n_right = self.info['params_waveformextractor']['n_right']
        
        peak_sign = self.info['params_peakdetector']['peak_sign']
        
        peak_width = n_right - n_left
        
        if index is not None:
            some_peaks_index = index
        else:
            if mode=='rand' and self.nb_peak>nb_max:
                some_peaks_index = np.random.choice(self.nb_peak, size=nb_max).astype('int64')
            elif mode=='rand' and self.nb_peak<=nb_max:
                some_peaks_index = np.arange(self.nb_peak, dtype='int64')
            elif mode=='all':
                some_peaks_index = np.arange(self.nb_peak, dtype='int64')
            else:
                raise(NotImplementedError, 'unknown mode')
        
        # this is important to not take 2 times the sames, this leads to bad mad/median
        some_peaks_index = np.unique(some_peaks_index)
        
        some_peak_mask = np.zeros(self.nb_peak, dtype='bool')
        some_peak_mask[some_peaks_index] = True
        
        nb = some_peaks_index.size
        
        # make it persitent
        #~ self.arrays.create_array('some_peaks_index', 'int64', (nb,), self.memory_mode)
        #~ self.some_peaks_index[:] = some_peaks_index
        self.arrays.add_array('some_peaks_index', some_peaks_index, self.memory_mode)
        
        shape=(nb, peak_width, self.nb_channel)
        self.arrays.create_array('some_waveforms', self.info['internal_dtype'], shape, self.memory_mode)

        seg_nums = np.unique(self.all_peaks['segment'])
        n = 0
        for seg_num in seg_nums:
            insegment_peaks  = self.all_peaks[some_peak_mask & (self.all_peaks['segment']==seg_num)]
            for peak in insegment_peaks:
                i_start = peak['index']+n_left
                i_stop = i_start+peak_width
                if align_waveform:
                    ratio = subsample_ratio
                    wf = self.dataio.get_signals_chunk(seg_num=seg_num, chan_grp=self.chan_grp, i_start=i_start-peak_width, i_stop=i_stop+peak_width, signal_type='processed')
                    wf2 = scipy.signal.resample(wf, wf.shape[0]*ratio, axis=0)
                    wf2_around_peak = wf2[(peak_width-n_left-2)*ratio:(peak_width-n_left+3)*ratio, :]
                    #~ print(wf2_around_peak.shape)
                    if peak_sign=='+':
                        #~ ind_chan_max = np.argmax(np.max(wf2_around_peak, axis=0))
                        ind_chan_max = np.argmax(wf2_around_peak[ratio, :])
                        ind_max = np.argmax(wf2_around_peak[:, ind_chan_max])
                    elif peak_sign=='-':
                        #~ ind_chan_max_old = np.argmin(np.min(wf2_around_peak, axis=0))
                        ind_chan_max = np.argmin(wf2_around_peak[ratio, :])
                        #~ print(ind_chan_max_old, ind_chan_max)
                        ind_max = np.argmin(wf2_around_peak[:, ind_chan_max])
                    shift = ind_max - ratio*2
                    #~ print('ind_chan_max', ind_chan_max, 'ind_max', ind_max, 'shift', shift)
                    
                    #~ i1=peak_width*ratio+ind_max
                    #~ i1_old = (peak_width-n_left-1)*ratio + ind_max + n_left*ratio 
                    #~ i1 = peak_width*ratio + shift
                    i1 = peak_width*ratio + shift
                    #~ print('i1_old', i1_old, 'i1', i1)
                    i2 = i1+peak_width*ratio
                    wf_short = wf2[i1:i2:ratio, :]
                    self.some_waveforms[n, :, :] = wf_short
                    
                    #DEBUG
                    #~ wf_short = self.dataio.get_signals_chunk(seg_num=seg_num, chan_grp=self.chan_grp, i_start=i_start, i_stop=i_stop, signal_type='processed')
                    #~ import matplotlib.pyplot as plt
                    #~ fig, ax = plt.subplots()
                    #~ ax.plot(wf2[:, ind_chan_max])
                    #~ x = (peak_width-n_left-2)*ratio + ind_max
                    #~ print(x, n_left, n_right, peak_width, ratio)
                    #~ y = wf2[(peak_width-n_left-2)*ratio+ind_max, ind_chan_max]
                    #~ y_av = wf2[(peak_width-n_left-2)*ratio+ind_max-ratio, ind_chan_max]
                    #~ y_af = wf2[(peak_width-n_left-2)*ratio+ind_max+ratio, ind_chan_max]
                    #~ ax.plot([x-ratio, x, x+ratio], [y_av, y, y_af], marker='o', markersize=10)
                    #~ ax.axvline((peak_width-n_left-2)*ratio)
                    #~ ax.axvline((peak_width-n_left+3)*ratio)
                    #~ ax.plot(np.arange(wf_short.shape[0])*ratio+peak_width*ratio, wf_short[:, ind_chan_max], ls='--')
                    #~ plt.show()
                    #END DEBUG
                    
                else:
                    wf = self.dataio.get_signals_chunk(seg_num=seg_num, chan_grp=self.chan_grp, i_start=i_start, i_stop=i_stop, signal_type='processed')
                    self.some_waveforms[n, :, :] = wf
                n +=1
        
        #Test smooth
        #~ box_size = 3
        #~ kernel = np.ones(box_size)/box_size
        #~ kernel = kernel[:, None, None]
        #~ self.some_waveforms[:] = scipy.signal.fftconvolve(self.some_waveforms, kernel,'same')
        
        self.info['params_waveformextractor'] = dict(n_left=n_left, n_right=n_right, 
                                                                nb_max=nb_max, align_waveform=align_waveform,
                                                                subsample_ratio=subsample_ratio)
        self.flush_info()
        
        #TODO recode this
        if self.projector is not None:
            try:
                self.apply_projection()
            except:
                print('can not project new waveforms maybe shape hace change')
                self.some_features = None
        else:
            self.some_features = None
    
    def find_good_limits(self, mad_threshold = 1.1, channel_percent=0.3, extract=True, min_left=-5, max_right=5):
        """
        Find goods limits for the waveform.
        Where the MAD is above noise level (=1.)
        
        The technics constists in finding continuous samples
        above 10% of backgroud noise for at least 30% of channels
        
        Parameters
        ----------
        mad_threshold: (default 1.1) threshold noise
        channel_percent:  (default 0.3) percent of channel above this noise.
        """
        
        old_n_left = self.info['params_waveformextractor']['n_left']
        old_n_right = self.info['params_waveformextractor']['n_right']

        median, mad = median_mad(self.some_waveforms, axis = 0)
        # any channel above MAD mad_threshold
        nb_above = np.sum(mad>=mad_threshold, axis=1)
        #~ print('nb_above', nb_above)
        #~ print('self.nb_channel*channel_percent', self.nb_channel*channel_percent)
        above = nb_above>=self.nb_channel*channel_percent
        #find max consequitive point that are True
        #~ print('above', above)
        
        
        up, = np.where(np.diff(above.astype(int))==1)
        down, = np.where(np.diff(above.astype(int))==-1)
        
        
        if len(up)==0 or len(down)==0:
            return None, None
        else:
            up = up[up<max(down)]
            down = down[down>min(up)]
            if len(up)==0 or len(down)==0:
                return None, None
            else:
                best = np.argmax(down-up)
                n_left = int(self.info['params_waveformextractor']['n_left'] + up[best])
                n_right = int(self.info['params_waveformextractor']['n_left'] + down[best]+1)
                #~ print(old_n_left, old_n_right)
                #~ print(n_left, n_right)
                
                n_left = min(n_left, min_left)
                n_right = max(n_right, max_right)
                #~ print(n_left, n_right)
                
                if extract:
                    self.projector = None
                    self.extract_some_waveforms(n_left=n_left, n_right=n_right, index=self.some_peaks_index, 
                                            align_waveform=self.info['params_waveformextractor']['align_waveform'])
                
                return n_left, n_right


    def extract_some_noise(self, nb_snippet=300):
        """
        Find some snipet of signal that are not overlap with peak waveforms.
        """
        #~ 'some_noise_index', 'some_noise_snippet', 
        assert  'params_waveformextractor' in self.info
        n_left = self.info['params_waveformextractor']['n_left']
        n_right = self.info['params_waveformextractor']['n_right']
        peak_width = n_right - n_left
        
        
        #~ self.all_peaks
        #~ _dtype_peak = [('index', 'int64'), ('label', 'int64'), ('segment', 'int64'),]
        
        some_noise_index = []
        n_by_seg = nb_snippet//self.dataio.nb_segment
        for seg_num in range(self.dataio.nb_segment):
            #~ length = self.dataio.get_segment_length(seg_num) #This is wrong
            length = self.info['processed_length']
            
            possibles = np.ones(length, dtype='bool')
            possibles[:peak_width] = False
            possibles[-peak_width:] = False
            peaks = self.all_peaks[self.all_peaks['segment']==seg_num]
            for peak in peaks:
                possibles[peak['index']+n_left-n_right:peak['index']+n_right-n_left]
            possible_indexes, = np.nonzero(possibles)
            noise_index = np.zeros(n_by_seg, dtype=_dtype_peak)
            noise_index['index'] = possible_indexes[np.sort(np.random.choice(possible_indexes.size, size=n_by_seg))]
            noise_index['label'] = labelcodes.LABEL_NOISE
            noise_index['segment'][:] = seg_num
            some_noise_index.append(noise_index)
        some_noise_index = np.concatenate(some_noise_index)
        
        #make it persistent
        self.arrays.add_array('some_noise_index', some_noise_index, self.memory_mode)
        
        #create snipet
        shape=(self.some_noise_index.size, peak_width, self.nb_channel)
        self.arrays.create_array('some_noise_snippet', self.info['internal_dtype'], shape, self.memory_mode)
        #~ n = 0
        for n, ind in enumerate(self.some_noise_index):
        #~ for seg_num in range(self.dataio.nb_segment):
            #~ insegment_indexes  = self.some_noise_index[(self.some_noise_index['segment']==seg_num)]
            #~ for ind in insegment_indexes:
            i_start = ind['index']+n_left
            i_stop = i_start+peak_width
            snippet = self.dataio.get_signals_chunk(seg_num=ind['segment'], chan_grp=self.chan_grp, i_start=i_start, i_stop=i_stop, signal_type='processed')
            self.some_noise_snippet[n, :, :] = snippet
                #~ n +=1

    def extract_some_features(self, method='pca', selection = None, **params): #n_components=5, 
        """
        params:
        n_components
        
        """
        #TODO selection
        
        #~ wf = self.some_waveforms.reshape(self.some_waveforms.shape[0], -1)
        #~ params['n_components'] = n_components
        features, channel_to_features, self.projector = decomposition.project_waveforms(self.some_waveforms, method=method, selection=None,
                    catalogueconstructor=self, **params)
        
        #trick to make it persistant
        #~ self.arrays.create_array('some_features', self.info['internal_dtype'], features.shape, self.memory_mode)
        #~ self.some_features[:] = features
        self.arrays.add_array('some_features', features.astype(self.info['internal_dtype']), self.memory_mode)
        self.arrays.add_array('channel_to_features', channel_to_features, self.memory_mode)
        
        if self.some_noise_snippet is not None:
            some_noise_features = self.projector.transform(self.some_noise_snippet)
            self.arrays.add_array('some_noise_features', some_noise_features.astype(self.info['internal_dtype']), self.memory_mode)
    
    #ALIAS TODO remove it
    project = extract_some_features
    
    def apply_projection(self):
        assert self.projector is not None
        features = self.projector.transform(self.some_waveforms)
        
        #trick to make it persistant
        #~ self.arrays.create_array('some_features', self.info['internal_dtype'], features.shape, self.memory_mode)
        #~ self.some_features[:] = features
        self.arrays.add_array('some_features', some_features.astype(self.info['internal_dtype']), self.memory_mode)
        
    
    
    def find_clusters(self, method='kmeans', selection=None, **kargs):
        #done in a separate module cluster.py
        cluster.find_clusters(self, method=method, selection=selection, **kargs)
        
        
        self.on_new_cluster()
        
        
        
        
        
        #~ if order_clusters:
            #~ self.order_clusters()
    
    
    def on_new_cluster(self):
        #~ print('on_new_cluster')
        if self.all_peaks is None:
            return
        cluster_labels = np.unique(self.all_peaks['label'])
        clusters = np.zeros(cluster_labels.shape, dtype=_dtype_cluster)
        clusters['cluster_label'][:] = cluster_labels
        clusters['cell_label'][:] = cluster_labels
        clusters['max_on_channel'][:] = -1
        clusters['max_peak_amplitude'][:] = np.nan
        clusters['waveform_rms'][:] = np.nan
        for i, k in enumerate(cluster_labels):
            clusters['nb_peak'][i] = np.sum(self.all_peaks['label']==k)
        
        if self.clusters is not None:
            #get previous cell_label
            for i, c in enumerate(clusters):
                #~ print(i, c)
                if c['cluster_label'] in self.clusters['cluster_label']:
                    j = np.nonzero(c['cluster_label']==self.clusters['cluster_label'])[0][0]
                    self.clusters[j]['cell_label'] in cluster_labels
                    clusters[i]['cell_label'] = self.clusters[j]['cell_label']
                    #~ print('j', j)
        
        if clusters.size>0:
            self.arrays.add_array('clusters', clusters, self.memory_mode)
    
    def compute_centroid(self, label_changed=None):
        if label_changed is None:
            # recompute all clusters
            self.centroids = {}
            label_changed = self.cluster_labels
        print('compute_centroid')
        
        if self.some_waveforms is None:
            return 
        n_left = int(self.info['params_waveformextractor']['n_left'])
        t1 = time.perf_counter()
        for k in label_changed:
            if k <0: continue
            if k not in self.cluster_labels:
                self.centroids.pop(k)
                continue
            wf = self.some_waveforms[self.all_peaks['label'][self.some_peaks_index]==k]
            median, mad = median_mad(wf, axis = 0)
            mean, std = np.mean(wf, axis=0), np.std(wf, axis=0)
            #~ max_on_channel = np.argmax(np.max(np.abs(mean), axis=0))
            max_on_channel = np.argmax(np.abs(median[-n_left,:]), axis=0)
            #~ print('k', k, max_on_channel)
            #~ print(median.shape)
            #~ fig, ax = plt.subplots()
            #~ ax.plot(median.T.flatten())
            #~ ax.axvspan(max_on_channel*median.shape[0], (max_on_channel+1)*median.shape[0], alpha=.2)
            #~ plt.show()
            self.centroids[k] = {'median':median, 'mad':mad, #'max_on_channel' : max_on_channel, 
                        'mean': mean, 'std': std}
            
            ind = np.nonzero(self.clusters['cluster_label']==k)[0][0]
            self.clusters['max_on_channel'][ind] = max_on_channel
            self.clusters['max_peak_amplitude'][ind] = median[-n_left, max_on_channel]
            self.clusters['waveform_rms'][ind] = np.sqrt(np.mean(median**2))

        self.arrays.flush_array('clusters')
        
        t2 = time.perf_counter()
        print('compute_centroid', t2-t1)
        
    
    def refresh_colors(self, reset=True, palette = 'husl'):
        if reset:
            self.colors = {}
        
        labels_ok = self.cluster_labels[self.cluster_labels>=0]
        n = labels_ok.size
        color_table = sns.color_palette(palette, n)
        for i, k in enumerate(labels_ok):
            if k not in self.colors:
                self.colors[k] = color_table[i]
        
        self.colors[labelcodes.LABEL_TRASH] = (.4, .4, .4)
        self.colors[labelcodes.LABEL_UNCLASSIFIED] = (.6, .6, .6)
        self.colors[labelcodes.LABEL_NOISE] = (.8, .8, .8)
    
    def split_cluster(self, label, method='kmeans',  **kargs): #order_clusters=True,
        mask = self.all_peaks['label']==label
        self.find_clusters(method=method, selection=mask, **kargs) # order_clusters=order_clusters,
    
    def trash_small_cluster(self, n=10):
        for k in self.cluster_labels:
            mask = self.all_peaks['label']==k
            if np.sum(mask)<=n:
                self.all_peaks['label'][mask] = -1
        self.on_new_cluster()

    def compute_spike_waveforms_similarity(self, method='cosine_similarity', size_max = 1e7):
        """This compute the similarity spike by spike.
        """
        t1 = time.perf_counter()
        spike_waveforms_similarity = None
        if self.some_waveforms is not None:
            wf = self.some_waveforms
            wf = wf.reshape(wf.shape[0], -1)
            if wf.size<size_max:
                spike_waveforms_similarity = metrics.compute_similarity(wf, method)
        
        if spike_waveforms_similarity is None:
            self.arrays.detach_array('spike_waveforms_similarity')
            self.spike_waveforms_similarity = None
        else:
            self.arrays.add_array('spike_waveforms_similarity', spike_waveforms_similarity.astype('float32'), self.memory_mode)

        t2 = time.perf_counter()
        print('compute_spike_waveforms_similarity', t2-t1)
        
        return self.spike_waveforms_similarity

    def compute_cluster_similarity(self, method='cosine_similarity_with_max'):
        if not hasattr(self, 'centroids'):
            self.compute_centroid()            
        #~ print('compute_cluster_similarity')
        t1 = time.perf_counter()
        
        labels = self.positive_cluster_labels
        wfs = np.array([self.centroids[k]['median'] for k in labels])
        wfs = wfs.reshape(wfs.shape[0], -1)
        if wfs.size == 0:
            cluster_similarity = None
        else:
            cluster_similarity = metrics.cosine_similarity_with_max(wfs)

        if cluster_similarity is None:
            self.arrays.detach_array('cluster_similarity')
            self.cluster_similarity = None
        else:
            self.arrays.add_array('cluster_similarity', cluster_similarity.astype('float32'), self.memory_mode)

        t2 = time.perf_counter()
        print('compute_cluster_similarity', t2-t1)

            

    def detect_high_similarity(self, threshold=0.95):
        if self.cluster_similarity is None:
            self.compute_cluster_similarity()
        pairs = get_pairs_over_threshold(self.cluster_similarity, self.positive_cluster_labels, threshold)
        return pairs
    
    def compute_cluster_ratio_similarity(self, method='cosine_similarity_with_max'):
        #~ print('compute_cluster_ratio_similarity')
        if not hasattr(self, 'centroids'):
            self.compute_centroid()            
        
        t1 = time.perf_counter()
        labels = self.positive_cluster_labels
        
        #TODO: this is stupid because cosine_similarity is the same at every scale!!!
        #so this is identique to compute_similarity()
        #find something else
        wf_normed = []
        for ind, k in enumerate(self.clusters['cluster_label']):
            if k<0: continue
            #~ chan = self.centroids[k]['max_on_channel']
            chan = self.clusters['max_on_channel'][ind]
            median = self.centroids[k]['median']
            n_left = int(self.info['params_waveformextractor']['n_left'])
            wf_normed.append(median/np.abs(median[-n_left, chan]))
        wf_normed = np.array(wf_normed)
        
        if wf_normed.size == 0:
            cluster_ratio_similarity = None
        else:
            wf_normed_flat = wf_normed.swapaxes(1, 2).reshape(wf_normed.shape[0], -1)
            #~ cluster_ratio_similarity = metrics.compute_similarity(wf_normed_flat, 'cosine_similarity')
            cluster_ratio_similarity = metrics.cosine_similarity_with_max(wf_normed_flat)

        if cluster_ratio_similarity is None:
            self.arrays.detach_array('cluster_ratio_similarity')
            self.cluster_ratio_similarity = None
        else:
            self.arrays.add_array('cluster_ratio_similarity', cluster_ratio_similarity.astype('float32'), self.memory_mode)
        #~ return labels, ratio_similarity, wf_normed_flat


        t2 = time.perf_counter()
        print('compute_cluster_ratio_similarity', t2-t1)        
        

    def detect_similar_waveform_ratio(self, threshold=0.9):
        if self.cluster_ratio_similarity is None:
            self.compute_cluster_ratio_similarity()
        pairs = get_pairs_over_threshold(self.cluster_ratio_similarity, self.positive_cluster_labels, threshold)
        return pairs
    
    def compute_spike_silhouette(self, size_max=1e7):
        t1 = time.perf_counter()
        
        spike_silhouette = None
        wf = self.some_waveforms
        if wf is not None:
            wf = wf.reshape(wf.shape[0], -1)
            labels = self.all_peaks['label'][self.some_peaks_index]
            if wf.size<size_max:
                spike_silhouette = metrics.compute_silhouette(wf, labels, metric='euclidean')

        if spike_silhouette is None:
            self.arrays.detach_array('spike_silhouette')
            self.spike_silhouette = None
        else:
            self.arrays.add_array('spike_silhouette', spike_silhouette.astype('float32'), self.memory_mode)


        t2 = time.perf_counter()
        print('compute_spike_silhouette', t2-t1)                
    
    def tag_same_cell(self, labels_to_group):
        inds, = np.nonzero(np.in1d(self.clusters['cluster_label'], labels_to_group))
        self.clusters['cell_label'][inds] = min(labels_to_group)
        
        
    
    def order_clusters(self, by='waveforms_rms'):
        """
        This reorder labels from highest rms to lower rms.
        The higher rms the smaller label.
        Negative labels are not reassigned.
        """
        
        if not hasattr(self, 'centroids'):
            self.compute_centroid()
        
        clusters = self.clusters.copy()
        neg_clusters = clusters[clusters['cluster_label']<0]
        pos_clusters = clusters[clusters['cluster_label']>=0]
        
        print(by)
        if by=='waveforms_rms':
            order = np.argsort(pos_clusters['waveform_rms'])[::-1]
        elif by=='max_peak_amplitude':
            order = np.argsort(np.abs(pos_clusters['max_peak_amplitude']))[::-1]
        else:
            raise(NotImplementedError)
        
        sorted_labels = pos_clusters['cluster_label'][order]
        
        #reassign labels for peaks and clusters
        N = int(max(sorted_labels)*10)
        self.all_peaks['label'][self.all_peaks['label']>=0] += N
        for new, old in enumerate(sorted_labels+N):
            self.all_peaks['label'][self.all_peaks['label']==old] = new
        
        pos_clusters = pos_clusters[order].copy()
        n = pos_clusters.size
        pos_clusters['cluster_label'] = np.arange(n)
        
        #this shoudl preserve previous identique cell_label
        pos_clusters['cell_label'] += N
        for i in range(n):
            k = pos_clusters['cell_label'][i]
            inds, = np.nonzero(pos_clusters['cell_label']==k)
            if (len(inds)>=1) and (inds[0] == i):
                pos_clusters['cell_label'][inds] = i
        new_cluster = np.concatenate((neg_clusters, pos_clusters))
        self.clusters[:] = new_cluster
    
    def make_catalogue(self):
        #TODO: offer possibility to resample some waveforms or choose the number
        
        t1 = time.perf_counter()
        self.catalogue = {}
        
        self.catalogue = {}
        self.catalogue['chan_grp'] = self.chan_grp
        n_left = self.catalogue['n_left'] = int(self.info['params_waveformextractor']['n_left'] +2)
        self.catalogue['n_right'] = int(self.info['params_waveformextractor']['n_right'] -2)
        self.catalogue['peak_width'] = self.catalogue['n_right'] - self.catalogue['n_left']
        
        cluster_labels = np.array(self.cluster_labels[self.cluster_labels>=0], copy=True)
        self.catalogue['cluster_labels'] = cluster_labels
        
        n, full_width, nchan = self.some_waveforms.shape
        centers0 = np.zeros((len(cluster_labels), full_width - 4, nchan), dtype=self.info['internal_dtype'])
        centers1 = np.zeros_like(centers0)
        centers2 = np.zeros_like(centers0)
        self.catalogue['centers0'] = centers0 # median of wavforms
        self.catalogue['centers1'] = centers1 # median of first derivative of wavforms
        self.catalogue['centers2'] = centers2 # median of second derivative of wavforms
        
        subsample = np.arange(1.5, full_width-2.5, 1/20.)
        self.catalogue['subsample_ratio'] = 20
        interp_centers0 = np.zeros((len(cluster_labels), subsample.size, nchan), dtype=self.info['internal_dtype'])
        self.catalogue['interp_centers0'] = interp_centers0
        
        #~ print('peak_width', self.catalogue['peak_width'])
        
        self.catalogue['label_to_index'] = {}
        for i, k in enumerate(cluster_labels):
            self.catalogue['label_to_index'][k] = i
            
            #print('construct_catalogue', k)
            # take peak of this cluster
            # and reshaape (nb_peak, nb_channel, nb_csample)
            #~ wf = self.some_waveforms[self.all_peaks['label']==k]
            wf0 = self.some_waveforms[self.all_peaks['label'][self.some_peaks_index]==k]
            
            
            #compute first and second derivative on dim=1 (time)
            kernel = np.array([1,0,-1])/2.
            kernel = kernel[None, :, None]
            wf1 =  scipy.signal.fftconvolve(wf0,kernel,'same') # first derivative
            wf2 =  scipy.signal.fftconvolve(wf1,kernel,'same') # second derivative
            
            #median and
            #eliminate margin because of border effect of derivative and reshape
            center0 = np.median(wf0, axis=0)
            centers0[i,:,:] = center0[2:-2, :]
            centers1[i,:,:] = np.median(wf1, axis=0)[2:-2, :]
            centers2[i,:,:] = np.median(wf2, axis=0)[2:-2, :]
            #~ center0 = np.mean(wf0, axis=0)
            #~ centers0[i,:,:] = center0[2:-2, :]
            #~ centers1[i,:,:] = np.mean(wf1, axis=0)[2:-2, :]
            #~ centers2[i,:,:] = np.mean(wf2, axis=0)[2:-2, :]

            #interpolate centers0 for reconstruction inbetween bsample when jitter is estimated
            f = scipy.interpolate.interp1d(np.arange(full_width), center0, axis=0, kind='cubic')
            oversampled_center = f(subsample)
            interp_centers0[i, :, :] = oversampled_center
            
            #~ fig, ax = plt.subplots()
            #~ ax.plot(np.arange(full_width-4), center0[2:-2, :], color='b', marker='o')
            #~ ax.plot(subsample-2.,oversampled_center, color='c')
            #~ plt.show()
            
        #find max  channel for each cluster for peak alignement
        self.catalogue['max_on_channel'] = np.zeros_like(self.catalogue['cluster_labels'])
        for i, k in enumerate(cluster_labels):
            center = self.catalogue['centers0'][i,:,:]
            self.catalogue['max_on_channel'][i] = np.argmax(np.abs(center[-n_left,:]), axis=0)
        
        #colors
        if not hasattr(self, 'colors'):
            self.refresh_colors()
        self.catalogue['cluster_colors'] = {}
        self.catalogue['cluster_colors'].update(self.colors)
        
        #params
        self.catalogue['params_signalpreprocessor'] = dict(self.info['params_signalpreprocessor'])
        self.catalogue['params_peakdetector'] = dict(self.info['params_peakdetector'])
        self.catalogue['signals_medians'] = np.array(self.signals_medians, copy=True)
        self.catalogue['signals_mads'] = np.array(self.signals_mads, copy=True)

        
        
        t2 = time.perf_counter()
        print('construct_catalogue', t2-t1)
        
        return self.catalogue
    
    def save_catalogue(self):
        self.make_catalogue()
        
        #~ filename = os.path.join(self.catalogue_path, 'initial_catalogue.pickle')
        #~ with open(filename, mode='wb') as f:
            #~ pickle.dump(self.catalogue, f)
        self.dataio.save_catalogue(self.catalogue, name='initial')
        
    
    #~ def load_catalogue(self):
        #~ filename = os.path.join(self.catalogue_path, 'initial_catalogue.pickle')
        #~ assert os.path.exists(filename), 'No catalogue file is found'
        #~ with open(filename, mode='rb') as f:
            #~ self.catalogue = pickle.load(f)
        #~ return self.catalogue

        #~ print('!!!! CatalogueConstructor.load_catalogue WILL BE REMOVED!!!!!')
        #~ self.catalogue = self.dataio.load_catalogue(name='initial')
        #~ return 

