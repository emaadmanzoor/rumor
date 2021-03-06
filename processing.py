import colorsys
import copy
import datetime
import numpy as np
import matplotlib.pyplot as plt
import sys
import util

from math import log, exp, sqrt, ceil
from subprocess import call
from time import sleep
from timeseries import *

try:
  from gexf import Gexf
  Gexf_loaded = True
except ImportError:
  Gexf_loaded = False

np.seterr(all = 'raise')

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def compute_rumor_tree_edges(statuses, edges, window):
  rumor_edges=[]
  parent={}
  for edge in edges:
    u = edge[0]
    v = edge[1]
    status_v = statuses[v]
    status_u = statuses[u]
    if status_v == None or status_u == None:
      continue
    if len(status_v) < 4 or len(status_u) < 4:
      continue
    if status_v[3] == '' or status_u[3] == '':
      continue
    # Compare timestamps
    try:
      t_v = util.datetime_to_epoch_seconds(status_v[3])
      t_u = util.datetime_to_epoch_seconds(status_u[3])
    except ValueError:
      print "Can't convert one or both of these to a timestamp:\n", \
          status_v[3], '\n', status_u[3]
    t_diff = t_u - t_v
    if t_diff <= window and t_diff > 0:
      if u not in parent:
        parent[u] = (v, t_v, t_u)
      else:
        parent_u = parent[u]
        # Replace parent if there is a more recent parent
        if t_v > parent_u[1]:
          parent[u] = (v, t_v, t_u)
    elif -t_diff <= window and t_diff < 0:
      if v not in parent:
        parent[v] = (u, t_u, t_v)
      else:
        parent_v = parent[v]
        # Replace parent if there is a more recent parent
        if t_u > parent_v[1]:
          parent[v] = (u, t_u, t_v)

  rumor_edges = [ (parent[a][0],a,parent[a][2]) for a in parent ]
  for r in rumor_edges:
    print r
  rumor_edges.sort(util.timestamped_edge_comparator)
  return rumor_edges

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
# An edge (v,u) is a rumor edge iff (u,v) is in edges (i.e. u follows
# v) and if t_u - t_v <= window
def compute_rumor_edges(statuses, edges, window):
  rumor_edges = []
  for edge in edges:
    u = edge[0]
    v = edge[1]
    status_v = statuses[v]
    status_u = statuses[u]
    if status_v == None or status_u == None:
      continue
    if len(status_v) < 4 or len(status_u) < 4:
      continue
    if status_v[3] == '' or status_u[3] == '':
      continue
    # Compare timestamps
    try:
      t_v = util.datetime_to_epoch_seconds(status_v[3])
      t_u = util.datetime_to_epoch_seconds(status_u[3])
    except ValueError:
      print "Can't convert one or both of these to a timestamp:\n", \
        status_v[3], '\n', status_u[3]
    t_diff = t_u - t_v
    if t_diff <= window and t_diff > 0:
      rumor_edges.append((v, u, t_u))
    elif -t_diff <= window and t_diff < 0:
      rumor_edges.append((u, v, t_v))

  rumor_edges.sort(util.timestamped_edge_comparator,'descend')
  return rumor_edges

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
# Take statuses and edges sorted by timestamp and simulate the rumor
# forward in time.
def simulate(rumor, step_mode = 'time', step = 10, limit = 2400):
  rumor_edges = rumor['edges']
  rumor_statuses = rumor['statuses']
  trend_onset = rumor['trend_onset']

  # Figure
  plt.figure()

  # Time series
  max_sizes = []
  total_sizes = []
  component_nums = []
  entropies = []
  max_component_ratios = []
  timestamps = []

  min_time = min([ edge[2] for edge in rumor_edges ])
  if step_mode == 'time':
    next_time = min_time
  max_pos = limit

  print 'time\t\teid\t\tpos\t\t|C_max|\t\tN(C)\t\ttime-trend_onset'

  components = {}
  node_to_component_id = {}
  adj={}

  # Set to keep track of statuses that gain many inbound edges at the same
  # time. This happens when a user follows lots of people that have mentioned
  # the topic, then tweets about the topic gets all of those followees as
  # parents, causing a sharp spike in the component growth

  # spikeset = set()

  for eid, edge in enumerate(rumor_edges):
    # print edge
    # print components
    # print node_to_component_id

    # Update adjacency list
    if edge[0] in adj:
      adj[edge[0]].append(edge[1])
    else:
      adj[edge[0]]=[edge[1]]
    
    # Update components
    if edge[0] not in node_to_component_id and edge[1] not in \
        node_to_component_id:
      # Create new component with id edge[0] (i.e. first node belonging to that
      #  component)
      component_id = edge[0]
      # print 'Creating new component ', component_id, ' from ', edge[0], ' and
      # ', edge[1]
      members = set([edge[0], edge[1]])
      components[edge[0]] = members
      node_to_component_id[edge[0]] = component_id
      node_to_component_id[edge[1]] = component_id
    elif edge[0] not in node_to_component_id:
      c1 = node_to_component_id[edge[1]]
      # print 'Adding ', edge[0], ' to ', c1, ': ', components[c1]
      # raw_input('')
      components[c1].add(edge[0])
      node_to_component_id[edge[0]] = c1
    elif edge[1] not in node_to_component_id:
      c0 = node_to_component_id[edge[0]]
      # print 'Adding ', edge[1], ' to ', c0, ': ', components[c0]
      # raw_input('')
      components[c0].add(edge[1])
      node_to_component_id[edge[1]] = c0
    else:
      c0 = node_to_component_id[edge[0]]
      c1 = node_to_component_id[edge[1]]
      if c0 != c1:
        # Merge components.
        members = components[c1]
        # print 'Merging\n', c0, ': ', components[c0], '\ninto\n', c1, ': ',
        # components[c1], '\n' raw_input('')
        for member in components[c0]:
          members.add(member)
          node_to_component_id[member] = c1
        components.pop(c0)
    
    """
    # Pause when you have some number of repeat statuses in a row (meaning that
    # lots of edges that terminate in that status suddenly got created)
    repeat_num = 2
    status_id = rumor_statuses[rumor_edges[eid][1]][0]
    if eid > repeat_num and \ 
        last_k_statuses_equal(status_id, rumor_statuses,rumor_edges, eid, repeat_num) and \
        status_id not in spikeset:
      print (rumor_statuses[rumor_edges[eid][0]], \ 
        rumor_statuses[rumor_edges[eid][1]])
      spikeset.add(status_id)
      raw_input()
    """

    if step_mode == 'index':
      pos = eid
    elif step_mode == 'time':
      pos = edge[2] - min_time
        
    if pos > limit:
      break

    if step_mode == 'index' and eid % step:
      continue
    if step_mode == 'time':
      if edge[2] < next_time:
        continue
      else:
        next_time = edge[2] + step

    component_sizes = []
    # raw_input('======================================================'
    for cid, members in components.items():
      component_sizes.append(len(members))
      # print 'component ', cid, ' size: ', len(members)  
      # raw_input('-------------------')

    time_after_onset = None
    if trend_onset is not None:
      time_after_onset = edge[2] - trend_onset

    print edge[2] - min_time, '\t\t', eid, '\t\t', pos, '/', limit, '\t\t', max(component_sizes), '\t\t', len(components), '\t\t', time_after_onset
    # Print largest adjacency list sizes.
    neighbor_counts=[ len(adj[k]) for k in adj ]
    sorted_idx=range(len(neighbor_counts))
    sorted_idx.sort(lambda x, y: neighbor_counts[y] - neighbor_counts[x])
    for itop in xrange(10):
      if itop>=len(sorted_idx):
        break
      print adj.keys()[sorted_idx[itop]], ':', neighbor_counts[sorted_idx[itop]]
    raw_input()

    # Desc sort of component sizes
    component_sizes.sort()
    component_sizes.reverse()

    # Append to timeseries
    max_sizes.append(max(component_sizes))
    total_sizes.append(sum(component_sizes))
    component_nums.append(len(component_sizes))
    entropies.append(util.entropy(component_sizes))
    if trend_onset is None:
      trend_onset = 0
    timestamps.append((edge[2] - trend_onset) / (60 * 60))
    max_component_ratios.append(float(max(component_sizes))/sum(component_sizes))
    shifted_ind = np.linspace(1, 1 + len(component_sizes), len(component_sizes))

    if eid > 0:
      color = util.step_to_color(pos, max_pos)
      plt.subplot(331)
      plt.loglog(shifted_ind, component_sizes, color = color, hold = 'on')
      plt.title('Loglog desc component sizes')

      plt.subplot(332)
      plt.semilogy(timestamps[-1], max_sizes[-1], 'ro', color = color,
                   hold = 'on')
      plt.title('Max component size')
      plt.xlabel('time (hours)')

      plt.subplot(333)
      plt.semilogy(timestamps[-1], total_sizes[-1], 'ro', color = color,
                   hold = 'on')
      plt.title('Total network size')
      plt.xlabel('time (hours)')

      plt.subplot(334)
      plt.plot(timestamps[-1], entropies[-1], 'go', color = color, hold = 'on')
      plt.title('Entropy of desc component sizes')
      plt.xlabel('time (hours)')

      plt.subplot(335)
      plt.semilogy(timestamps[-1], component_nums[-1], 'ko', color = color,
                   hold = 'on')
      plt.title('Number of components')
      plt.xlabel('time (hours)')

      plt.subplot(336)
      plt.loglog(shifted_ind, np.cumsum(component_sizes), color = color,
                 hold = 'on')
      plt.title('Cum. sum. of desc component sizes')

      plt.subplot(337)
      plt.plot(timestamps[-1], max_component_ratios[-1], 'ko', color = color,
               hold = 'on')
      plt.title('Max comp size / Total network Size')
      plt.xlabel('time (hours)')

    # plt.hist(component_sizes, np.linspace(0.5, 15.5, 15))
    # plt.plot(np.cumsum(np.histogram(component_sizes, bins = np.linspace(0.5,
    # 15.5, 15))[0]), hold = 'on')
    if not eid % 15*step:
      pass#plt.pause(0.001)
  plt.show()
  return components

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def last_k_statuses_equal(equals_val, rumor_statuses, rumor_edges,
                          curr_idx, k):
  for i in xrange(k):
    if rumor_statuses[rumor_edges[curr_idx-i][1]][0] is not equals_val:
      return False
  return True

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
# DETECTION
#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_eval_for_param(ts_info_pos, ts_info_neg, threshold, trend_times = None):
  ts_norm_func = ts_mean_median_norm_func(1, 0)
  detection_results = ts_detect(ts_info_pos = ts_info_pos,
                                ts_info_neg = ts_info_neg,
                                threshold = threshold,
                                test_frac = 0.25,
                                ts_norm_func = ts_norm_func)
  detections = detection_results['detection']
  lates = []
  earlies = []
  tp = 0
  fn = 0
  for topic in detections['pos']:
    if len(detections['pos'][topic]['times']) > 0:
      tp += 1
      detection_time = min(detections['pos'][topic]['times'])
      onset_time = ts_info_pos[topic]['trend_start']
      if detection_time > onset_time:
        lates.append(detection_time - onset_time)
      else:
        earlies.append(onset_time - detection_time)
    else:
      fn += 1
  fp = 0
  tn = 0
  for topic in detections['neg']:
    if len(detections['neg'][topic]['times']) > 0:
      fp += 1
    else:
      tn += 1

  print 'total pos = ', len(detections['pos'])
  print 'total neg = ', len(detections['neg'])
  print 'total = ', len(detections['neg']) + len(detections['pos'])
  print 'tp = ', tp 
  print 'fn = ', fn 
  print 'fp = ', fp 
  print 'tn = ', tn
  print 'fpr = ', (float(fp) / (fp + tn))
  print 'tpr = ', (float(tp) / (fn + tp))
  avg_early = None
  std_early = None
  avg_late = None
  std_late = None
  if len(earlies) > 0:
    avg_early = np.mean(earlies) / (3600 * 1000)
    std_early = np.std(earlies) / (3600 * 1000)
  if len(lates) > 0:
    avg_late = np.mean(lates) / (3600 * 1000)
    std_late = np.std(lates) / (3600 * 1000)
  print 'avg. early = ', avg_early, 'hrs'
  print 'stdev. early = ', std_early, 'hrs'
  print 'avg. late = ', avg_late, 'hrs'
  print 'stdev. late = ', std_late, 'hrs'
  print 'earlies\n', earlies, 'hrs'
  print 'lates\n', lates, 'hrs'
  
  viz = True
  if viz:
    viz_detection(detection_results = detection_results,
                  trend_times = trend_times)
  
#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def viz_detection(ts_info_pos = None, ts_info_neg = None, trend_times = None,
                  detection_results = None, pos_filter = None,
                  neg_filter = None, first_only = True):
  # Get raw and normalized rates
  # Compare trend times, detection times, rates, normalized rates, scores
  
  if detection_results is None:
    ts_norm_func = ts_mean_median_norm_func(1, 0)
    detection_results = ts_detect(ts_info_pos, ts_info_neg, threshold = 5,
                                  test_frac = 0.25, ts_norm_func = ts_norm_func)

  detections = detection_results['detection']
  scores = detection_results['scores']
  signals = detection_results['signals']

  plt.ion()
  plt.close('all')

  tests = { 'pos': 'b', 'neg': 'r' }
  for test_type in tests:
    # Plot detection times vs actual trend times.
    for topic in detections[test_type]:
      if test_type is 'pos' and pos_filter is not None and topic not in pos_filter:
        continue
      if test_type is 'neg' and neg_filter is not None and topic not in neg_filter:
        continue

      topic_detection_scores = detections[test_type][topic]['scores']
      topic_detection_times = detections[test_type][topic]['times']
      score_values = scores[test_type][topic].values

      fig = plt.figure(figsize = (10,4))

      min_trend_time = 0
      if trend_times is not None:
        if test_type is 'pos':
          if topic in trend_times:
            topic_trending_times = trend_times[topic]
            times_to_plot = np.array(sorted(topic_trending_times)) / (1000 * 3600.0)
            if first_only:
              min_trend_time = times_to_plot[0]
              times_to_plot = np.array([times_to_plot[0]])
            plt.axvline(times_to_plot[0] - min_trend_time, color = 'k', lw = 0.5)

            markerline, stemlines, baseline = \
                plt.stem(times_to_plot - min_trend_time,
                         np.ones((len(times_to_plot), 1)))
            plt.hold(True)
            plt.setp(markerline, 'markerfacecolor', 'w', 'label', '$t_{onset}$')
            plt.setp(markerline, 'markeredgecolor', 'k')
            plt.setp(stemlines, 'color', 'k', 'linestyle', '--')

          else:
            print topic, ' not found in trending times dict.'

      if len(topic_detection_times) > 0:
        times_to_plot = np.array(sorted(topic_detection_times)) / (1000 * 3600.0)
        if first_only:
          times_to_plot = np.array([times_to_plot[0]])
        plt.axvline(times_to_plot[0] - min_trend_time, color = 'k', lw = 0.5)
        markerline, stemlines, baseline = \
            plt.stem(times_to_plot - min_trend_time,
                     np.ones((len(times_to_plot), 1)))
        plt.hold(True)

        plt.setp(markerline, 'markerfacecolor', tests[test_type], 'label', '$t_{detect}$')
        plt.setp(markerline, 'markeredgecolor', 'k')
        plt.setp(stemlines, 'color', tests[test_type])

      # Scores, signal, and threshold

      plt.semilogy(np.array(scores[test_type][topic].times) / (3600 * 1000.0) - min_trend_time,
               score_values, color = 'k', lw = 1, label = '$R(\mathbf{s})$')
      plt.title('Topic: ' + topic, size = 16)
      plt.hold(True)

      plt.axhline(1, color = 'k', ls = ':', label = r'$\theta$', lw = 0.5)
   
      fig.autofmt_xdate()
      #plt.xlabel('time after true onset (hours)')
      plt.xlabel('time (hours)', size = 16)
      plt.ylabel('$R(\mathbf{s})$', size = 16)
      plt.ylim(ymin = 0.1)

      time_range = (scores[test_type][topic].tmax - scores[test_type][topic].tmin) / (1000.0 * 3600)
      plt.xlim([scores[test_type][topic].tmin / (1000.0 * 3600) - time_range * 0.4 - min_trend_time,
                scores[test_type][topic].tmax / (1000.0 * 3600) + time_range * 0.3 - min_trend_time])

      plt.legend(scatterpoints = 1, loc = 2, frameon = False)
      plt.twinx()

      signal_values = np.array(signals[test_type][topic]['values'])
      #signal_values = signal_values - np.min(signal_values) + 0.1
      #signal_values = signal_values * (np.log(np.max(score_values)) / np.max(signal_values)) / 2.0
      plt.plot(np.array(signals[test_type][topic]['times']) / (1000 * 3600.0) - min_trend_time,
               signal_values, color = 'k', linestyle = '--', lw = 1, label = '$\mathbf{s}_{\infty}$')   
      plt.ylabel('$\mathbf{s}_{\infty}$', size = 16)
      plt.xlim([scores[test_type][topic].tmin / (1000.0 * 3600) - time_range * 0.4 - min_trend_time,
                scores[test_type][topic].tmax / (1000.0 * 3600) + time_range * 0.0 - min_trend_time])


      plt.legend(loc = 1, frameon = False)

      plt.draw()
      raw_input()      
  
#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_balance_data(ts_info_pos_orig, ts_info_neg_orig):
  topics_pos = ts_info_pos_orig.keys()
  topics_neg = ts_info_neg_orig.keys()

  ts_info_pos = {}
  ts_info_neg = {}
  # Balance the data
  if len(ts_info_pos_orig) > len(ts_info_neg_orig):
    more_pos = True
    r = (len(ts_info_pos_orig) - len(ts_info_neg_orig)) / \
        float(len(ts_info_pos_orig))
    for topic in topics_pos:
      if np.random.rand() > r:
        ts_info_pos[topic] = ts_info_pos_orig[topic]
    for topic in topics_neg:
      ts_info_neg[topic] = ts_info_neg_orig[topic]
  else:
    more_pos = False
    r = (len(ts_info_neg_orig) - len(ts_info_pos_orig)) / \
        float(len(ts_info_neg_orig))
    for topic in topics_neg:
      if np.random.rand() > r:
        ts_info_neg[topic] = ts_info_neg_orig[topic]
    for topic in topics_pos:
      ts_info_pos[topic] = ts_info_pos_orig[topic]

  return ts_info_pos, ts_info_neg

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_normalize(ts_info_orig, ts_norm_func, mode = 'offline', beta = 1):
  # TODO: This became really slow. Profile!!
  """
  if mode is 'offline':
    return dict([
        [ topic, { 'ts': Timeseries(ts_info_orig[topic]['ts'].times, 
                                    [ (v + 0.01) / (ts_norm_func(ts_info_orig[topic]['ts'].values) + 0.01) 
                                      for v in ts_info_orig[topic]['ts'].values ]),
                   'trend_start': ts_info_orig[topic]['trend_start'],
                   'trend_end': ts_info_orig[topic]['trend_end'] }] 
          for topic in ts_info_orig ])
  """

  # Normalize all timeseries
  ts_info = {}
  for (i, topic) in enumerate(ts_info_orig):
    print topic, ' ', (i + 1), '/', len(ts_info_orig)
    ts = ts_info_orig[topic]['ts']
    ts_info[topic] = {}
    if mode is 'online':
      norm_values = \
          [ ((ts.values[i] + 0.01) / (ts_norm_func(ts.values[0:i+1]) + 0.01)) ** beta
            for i in range(len(ts.values)) ]
    elif mode is 'offline':
      ts_norm = ts_norm_func(ts.values)
      norm_times = ts.times
      norm_values = \
          [ ((v + 0.01) / (ts_norm + 0.01)) ** beta for v in ts.values ]
    #ts_info[topic]['ts'] = Timeseries(norm_times, norm_values)
    ts_info[topic]['ts'] = Timeseries(norm_times, norm_values).ddt().abs().pow(1.2)
    ts_info[topic]['trend_start'] = ts_info_orig[topic]['trend_start']
    ts_info[topic]['trend_end'] = ts_info_orig[topic]['trend_end']
  return ts_info


#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_mean_median_norm_func(mean_weight, median_weight):
  func = lambda x: median_weight * np.median(x) + mean_weight * np.mean(x)
  return func

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_pnorm_func(p = 2):
  func = lambda x: np.linalg.norm(x, ord = p)
  return func

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
# Create timeseries bundles.
def ts_bundle(ts_info, detection_window_time, w_smooth = 25):
  bundle = {}
  # TODO should abstract away normalization.
  for topic in ts_info:
    ts = ts_info[topic]['ts']

    if ts_info[topic]['trend_start'] is None or \
          ts_info[topic]['trend_end'] is None:
      start = ts.tmin + \
          np.random.rand() * (ts.tmax - ts.tmin - detection_window_time)
      end = start + detection_window_time
    else:
      start = ts_info[topic]['trend_start'] - detection_window_time
      end =  ts_info[topic]['trend_start']

    tsw = ts.ts_in_window(start,end)
    # Add eps as a fudge factor, since we're taking log. TODO
    #bundle[topic] = Timeseries(tsw.times, np.cumsum(tsw.values) + 0.01)
    smoothed = np.convolve(tsw.values, np.ones(w_smooth,),
                           mode = 'full')
    # TODO: some methods depend on this being the raw signal, not the log!
    smoothed = [ log(v + 0.01) for v in smoothed[0:len(tsw.values)] ]
    #smoothed = [ (v + 0.01) for v in smoothed[0:len(tsw.values)] ]
    bundle[topic] = Timeseries(tsw.times, smoothed)
  return bundle

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_split_training_test(ts_info, test_frac):
  # Split into training and test
  ts_info_train = {}
  ts_info_test = {}
  topics = ts_info.keys()
  for topic in ts_info:
    if np.random.rand() < test_frac:
      ts_info_test[topic] = ts_info[topic]
    else:
      ts_info_train[topic] = ts_info[topic]
  return ts_info_train, ts_info_test

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_shift_detect(ts_info_pos, ts_info_neg, threshold = 1, test_frac = 0.25,
                    cmpr_window = 80, cmpr_step = None, w_smooth = 80, gamma = 1,
                    p_sample = 0.5, detection_step = None, min_dist_step = None,
                    detection_window_hrs = 5, req_consec_detections = 1,
                    normalize = True, pnt = False, stop_when_detected = True,
                    plot = False):

  #np.random.seed(31953)
  #np.random.seed(334513)

  # TODO: this is ugly...
  tstep = ts_info_pos[ts_info_pos.keys()[0]]['ts'].tstep

  if cmpr_window >= detection_window_hrs * 3600 * 1000 / float(tstep):
    # It doesn't make sense for the comparison window to be as big or bigger
    # than the detection window.
    return None

  if detection_step is None:
    # 10 detection steps.
    detection_step = int(
      ceil(
        (int(2 * detection_window_hrs * 3600 * 1000 / float(tstep)) - cmpr_window) / 10.0))
  if cmpr_step is None:
    # 5 points of comparison between trajectory pieces.
    cmpr_step = int(ceil(cmpr_window / 5.0))
  if min_dist_step is None:
    min_dist_step = int(
      ceil(
        (int(detection_window_hrs * 3600 * 1000 / float(tstep)) - cmpr_window) / 15.0))

  if pnt:
    print 'Sampling data...'
  ts_info_pos = ts_sample_topics(ts_info_pos, p_sample)
  ts_info_neg = ts_sample_topics(ts_info_neg, p_sample)

  if pnt:
    print 'Balancing data...'
  ts_info_pos, ts_info_neg = ts_balance_data(ts_info_pos, ts_info_neg)
  
  # Normalize all timeseries.
  if normalize:
    if pnt:
      print 'Normalizing...'
    # ts_norm_func = ts_mean_median_norm_func(0, 1)
    ts_norm_func = ts_pnorm_func(p = 1)
    ts_info_pos = ts_normalize(ts_info_pos, ts_norm_func, beta = 1)
    ts_info_neg = ts_normalize(ts_info_neg, ts_norm_func, beta = 1)

  if pnt:
    print 'Splitting into training and test...'
  ts_info_pos_train, ts_info_pos_test = ts_split_training_test(ts_info_pos,
                                                               test_frac)
  ts_info_neg_train, ts_info_neg_test = ts_split_training_test(ts_info_neg,
                                                               test_frac)
  # Construct smoothed timeseries.
  if pnt:
    print 'Creating bundles...'
  w_smooth = 60
  detection_window_time = detection_window_hrs * 3600 * 1000
  bundle_pos = ts_bundle(ts_info_pos_train, detection_window_time,
                         w_smooth = w_smooth)
  bundle_neg = ts_bundle(ts_info_neg_train, detection_window_time,
                         w_smooth = w_smooth)
  pos_topics_bundle = bundle_pos.keys()
  N_bundle = len(bundle_pos[pos_topics_bundle[0]].values)

  plt.ion()    

  if plot:
    plt.close('all')
    plt.figure(figsize = (10,10))
  # Run detection on each trajectory in the positive and negative test sets. For
  # the positive test trajectories, detection will be run in the interval of 2 *
  # detection_window_time centered at the trend onset. For negative test
  # trajectories, detection will be run for a randomly sampled interval of 2 *
  # detection_window_time.
  ts_info_tests = { 'pos': ts_info_pos_test, 'neg': ts_info_neg_test }
  bundles = { 'pos': bundle_pos, 'neg': bundle_neg }
  colors = { 'pos': 'b', 'neg': 'r' }

  fp = 0
  fn = 0
  tp = 0
  tn = 0
  earlies = []
  lates = []

  num_consec_detections = 0

  detection_results = {}
  detection_results['detection'] = {}
  detection_results['scores'] = {}
  detection_results['signals'] = {}

  if pnt:
    print 'Doing detection...'
  for test_type in ts_info_tests:
    detection_results['detection'][test_type] = {}
    detection_results['scores'][test_type] = {}
    detection_results['signals'][test_type] = {}

    if pnt:
      print '=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~'
      print '# Test type:', test_type
      print '=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~'
    ts_info_test = ts_info_tests[test_type]
    for (test_index, test_topic) in enumerate(ts_info_test):
      detection_results['detection'][test_type][test_topic] = {}
      detection_results['detection'][test_type][test_topic]['scores'] = []
      detection_results['detection'][test_type][test_topic]['times'] = []
      detection_results['signals'][test_type][test_topic] = {}
      detection_results['scores'][test_type][test_topic] = []
      score_values = []
      score_times = []

      if pnt:
        print '\nTest topic', test_topic, (test_index + 1), '/', \
            len(ts_info_test)
      detected = False

      tsobj = ts_info_test[test_topic]['ts']

      if test_type is 'pos':
        trend_start = ts_info_test[test_topic]['trend_start']
        tsobj_d = tsobj.ts_in_window(trend_start - detection_window_time,
                                     trend_start + detection_window_time)
      elif test_type is 'neg':
        # Randomly sample a detection interval of time 2 *
        # detection_window_time.
        detection_start = np.random.rand() * \
            (tsobj.tmax - tsobj.tmin - 2 * detection_window_time) + tsobj.tmin
        tsobj_d = tsobj.ts_in_window(
          detection_start,
          detection_start + 2 * detection_window_time)

      ts = tsobj_d.values

      # ts = (ts + 0.01) / (ts_norm_func(ts) + 0.01)
      ts_orig_len = len(ts)
      ts = np.convolve(ts, np.ones(w_smooth), 'full')
      ts = [ log(v + 0.01) for v in ts[0:ts_orig_len] ]
      detection_results['signals'][test_type][test_topic]['times'] = tsobj_d.times
      detection_results['signals'][test_type][test_topic]['values'] = ts
      """
      plt.plot(ts)
      plt.title('Smoothed and normalized timeseries for ' + test_topic)
      plt.hold(True)
      raw_input()
      """

      for i in np.arange(0, len(ts) - cmpr_window, detection_step):
        tsw = ts[i:i+cmpr_window]
        # Compute minimum distances to each curve
        min_dists = { 'pos': [], 'neg': []}
        for (bundle_index, bundle_type) in enumerate(bundles):
          bundle = bundles[bundle_type]
          for (train_index, train_topic) in enumerate(bundle):            
            dists = \
              [ ts_dist_func(
                  tsw,
                  bundle[train_topic].values[j:j+cmpr_window]) 
                for j in np.arange(0, N_bundle-cmpr_window, min_dist_step) ]
            jmin = np.argmin(dists)
            min_dist = dists[jmin]
            min_dists[bundle_type].append(min_dist)
            if plot:
              # Plot a random subset of trajectories to speed up plotting.
              plt.subplot(221)
              if np.random.rand() < 0.2:
                plt.plot(bundle[train_topic].values,
                         color = colors[bundle_type])
                plt.hold(True)
              # Plot only one copy of the trajectory in the comparison
              # window. Otherwise it is difficult to see it.
              if bundle_index == len(bundles) - 1 and \
                    train_index == len(bundle) - 1:
                plt.plot(np.arange(jmin,jmin+cmpr_window,1), tsw, color = 'k',
                         linewidth = 3, linestyle = '-')

        score = np.mean( [exp(-gamma * d) for d in min_dists['pos']] ) / \
            np.mean( [exp(-gamma * d) for d in min_dists['neg']] )

        if plot:
          #raw_input()
          plt.draw()
          plt.hold(False)

        if plot:
          plt.subplot(222)
          plt.plot(sorted(min_dists['pos']), 'b')
          plt.hold(True)
          plt.plot(sorted(min_dists['neg']), 'r')
          plt.title('Sorted distances')
          plt.hold(False)          

          plt.subplot(223)
          plt.plot(np.cumsum(
              [ exp(-gamma * d) for d in sorted(min_dists['pos']) ]), 'b')
          plt.hold(True)
          plt.plot(np.cumsum(
              [ exp(-gamma * d) for d in sorted(min_dists['neg']) ]), 'r')
          plt.hold(False)          

          plt.subplot(224)
          n, bins, patches = plt.hist(min_dists['pos'], bins = 50)
          plt.setp(patches, 'facecolor', (0,0,1), 'alpha', 0.25)
          plt.hold(True)
          n, bins, patches = plt.hist(min_dists['neg'], bins = 50)
          plt.setp(patches, 'facecolor', (1,0,0), 'alpha', 0.25)
          plt.title('Histograms of distances')
          plt.hold(False)           

        
        curr_time = tsobj_d.tmin + (i + cmpr_window - 1) * tsobj_d.tstep
        onset_time = tsobj_d.tmin + int(len(tsobj_d.values) / 2.0) * tsobj_d.tstep
        score_values.append(score)
        score_times.append(curr_time)
          
        if score < threshold:
          if pnt:
            print i, '/', (len(ts) - cmpr_window), score
            num_consec_detections = 0
        else:
          num_consec_detections += 1
          if pnt:
            print i, '/', (len(ts) - cmpr_window), score, '-----------o'
          if num_consec_detections >= req_consec_detections:
            num_consec_detections = 0
            detected = True
            # Detection and onset times (relative to start of detection window,
            # not absolute! TODO/WARNING: Since we are using indices instead of
            # explicit time, the correctness of these times depends on whether i
            # is iterating through the whole detection window or some
            # post-convolution slice of it.)
            detection_time = curr_time # i * tsobj_d.tstep
            #onset_time = tsobj_d.tstep * len(tsobj_d.values) / 2.0

            detection_results['detection'][test_type][test_topic]['scores'].append(score)
            detection_results['detection'][test_type][test_topic]['times'].append(detection_time)

            # Record late or early detection. Note that this only makes sense for
            # positive examples andwhen stop_when_detected is True.
            if test_type is 'pos':
              if detection_time > onset_time:
                lates.append(detection_time - onset_time)
              else:
                earlies.append(onset_time - detection_time)
            if stop_when_detected:
              break

        if plot:
          #raw_input()
          plt.draw()
          plt.hold(False)

      # If we go through the whole test signal and don't detect anything:
      detection_results['scores'][test_type][test_topic] = Timeseries(score_times, score_values)

      if detected:
        if test_type is 'pos':
          tp += 1
        else:
          fp += 1
      else:
        if test_type is 'pos':
          fn += 1
        else:
          tn += 1
          
      if pnt and not test_index % 1:
        print 'fp so far', fp
        print 'fn so far', fn
        print 'tp so far', tp
        print 'tn so far', tn
        if len(earlies) > 0:
          print 'mean early', np.mean(earlies) / (3600 * 1000)
          print 'std early', np.std(earlies) / (3600 * 1000)
        if len(lates) > 0:
          print 'mean late', np.mean(lates) / (3600 * 1000)
          print 'std late', np.std(lates) / (3600 * 1000)
        if tn + fp > 0:
          print 'fpr so far: ', (fp / float(tn + fp))
          """
          if test_type is 'neg':
            plt.scatter([test_index], [(fp / float(tn + fp))], c = 'r')
            plt.draw()
            plt.hold(True)
          """
        if fn + tp > 0:
          print 'tpr so far: ', (tp / float(fn + tp))
          """
          if test_type is 'pos':
            plt.scatter([test_index], [(tp / float(fn + tp))], c = 'b')
            plt.draw()
            plt.hold(True)
          """
   
  if tn + fp > 0:
    print 'final fpr: ', (fp / float(tn + fp))
  if fn + tp > 0:
    print 'final tpr: ', (tp / float(fn + tp))

  return { 'fp': fp,
           'tp': tp,
           'fn': fn,
           'tn': tn,
           'fpr': (fp / float(tn + fp)), 
           'tpr': (tp / float(fn + tp)),
           'earlies': earlies,
           'lates': lates,
           'detection_results': detection_results}
  
#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_dist_func(a, b, cmpr_step = 1):
  """
  i1 = int(np.random.rand() * len(a))
  i2 = int(np.random.rand() * len(a))
  if (a[i1] - b[i1]) ** 2 > 30 and abs(a[i2] - b[i2]) > 30:
    return 99999999.9
  """
  
  """
  if abs(max(a) - max(b)) + abs(min(a) - min(b)) > 200:
    return 999999.9
  """
  """
  return sqrt(sum( [ (a[i] - b[i]) ** 2 for i in range(len(b)) ] ))
  """
  return sqrt( sum( [ (a[i] - b[i]) ** 2 
                      for i in np.arange(0, len(b), cmpr_step) ]))

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_detect(ts_info_pos_orig, ts_info_neg_orig, threshold = 1,
              test_frac = 0.05, ts_norm_func = None):
  np.random.seed(31953)

  # Sample data
  print 'Sampling data...'
  p_sample = 0.1
  ts_info_pos = ts_sample_topics(ts_info_pos_orig, p_sample)
  ts_info_neg = ts_sample_topics(ts_info_neg_orig, p_sample)

  # TODO: different norm_funcs?

  print 'Balancing data...'
  ts_info_pos, ts_info_neg = ts_balance_data(ts_info_pos, ts_info_neg)
  
  ## Normalize whole timeseries a priori.
  # ts_info_pos = ts_normalize(ts_info_pos)
  # ts_info_neg = ts_normalize(ts_info_neg)
  
  print 'Splitting into training and test...'
  ts_info_pos_train, ts_info_pos_test = ts_split_training_test(ts_info_pos,
                                                               test_frac)
  ts_info_neg_train, ts_info_neg_test = ts_split_training_test(ts_info_neg,
                                                               test_frac)
  detection_interval_time = 5 * 60 * 1000
  detection_window_time = 12 * detection_interval_time

  ts_norm_func = ts_mean_median_norm_func(0.5, 0.5)
  # Normalize only training timeseries a priori (TODO: do it online)
  print 'Normalizing...'
  ts_info_pos_train = ts_normalize(ts_info_pos_train, ts_norm_func)
  ts_info_neg_train = ts_normalize(ts_info_neg_train, ts_norm_func)
  ts_norm_func = ts_mean_median_norm_func(0.5, 0.5)

  print 'Creating bundles...'
  bundle_pos = ts_bundle(ts_info_pos_train, detection_window_time)
  bundle_neg = ts_bundle(ts_info_neg_train, detection_window_time)

  results = {}
  results['scores'] = {}
  results['detection'] = {}
  detection = {}
  scores = {}

  # Test
  tests = {'pos' : {'ts_info' : ts_info_pos_test, 'color' : 'b'},
           'neg' : {'ts_info' : ts_info_neg_test, 'color' : 'r'}}

  stop_when_detected = False
  ignore_detection_far_from_onset = False
  ignore_detection_window = 6 * 1000 * 3600
  plot_hist = True
  plot_scores = False
  if plot_hist or plot_scores:
    plt.close('all')
    plt.ion()
    plt.figure()
    plt.hold(False)
    plt.show()

  # Number of contiguous samples to use to compare two volume trajectories.
  cmpr_window = 1
  for type in tests:
    detection[type] = {}
    scores[type] = {}
    for ti, topic in enumerate(tests[type]['ts_info']):
      print 'Topic: ', topic, '\t', ti + 1, '/', len(tests[type]['ts_info'])
      indices_tested = set()
      ts_test = tests[type]['ts_info'][topic]['ts']
      # Store scores at the end of each window
      topic_scores = []
      topic_score_times = []
      # Detection variables
      detected = False
      detection[type][topic] = {}
      detection[type][topic]['scores'] = []
      detection[type][topic]['times'] = []
      scores[type][topic] = []

      t_window_starts = np.arange(ts_test.tmin,
        ts_test.tmax - detection_window_time - detection_interval_time,
        detection_interval_time)
      for t_window_start in t_window_starts:
        if detected and stop_when_detected:
          break
        i_window_start = ts_test.time_to_index(t_window_start)
        # print 'Start index: ', i_window_start
        dt_detects = np.arange(detection_interval_time,
                               detection_window_time,
                               detection_interval_time)
        for dt_detect in dt_detects:
          if detected and stop_when_detected:
            break
          di_detect = ts_test.dtime_to_dindex(dt_detect)
          i_detect = i_window_start + di_detect
          if i_detect in indices_tested:
            continue
          indices_tested.add(i_detect)

          # print 'Offset: ', di_detect, '\tAbsolute: ', \
          #   (i_window_start + di_detect)

          # Compute score and do detection
          score_end_of_window_only = True
          test_rate = ts_test.values[0:i_window_start + di_detect]
          # TODO: decaying weights for online background model.
          test_rate_norm = ts_norm_func(test_rate)
          test_rate_in_window = [ v + 0.01 
            for v in ts_test.values[i_window_start:i_window_start + di_detect]]
          # TODO: abstract out the 0.01 trick in a separate normalization
          # method.
          test_trajectory = np.cumsum(
            test_rate_in_window / (test_rate_norm + 0.01))
          
          test_val = test_trajectory[-1]
          if dt_detect == max(dt_detects) or not score_end_of_window_only:
            score = detection_func(bundle_pos, bundle_neg, test_trajectory,
                                   len(test_trajectory) - 1, cmpr_window)
            topic_scores.append(score)
            topic_score_times.append(dt_detect + t_window_start)
            if score > threshold:
              detection_time = t_window_start + dt_detect
              onset_time = tests[type]['ts_info'][topic]['trend_start']
              record_detection = True
              if onset_time is not None and \
                  ignore_detection_far_from_onset and \
                  abs(detection_time - onset_time) > ignore_detection_window:
                record_detection = False
              if record_detection:
                detection[type][topic]['times'].append(detection_time)
                detection[type][topic]['scores'].append(score)
                detected = True
              sys.stdout.write('.')
            else:
              sys.stdout.write(' ')

          # Plots
          if plot_scores:
            if dt_detect == max(dt_detects) and \
                  t_window_start == max(t_window_starts):
              plt.plot(topic_score_times, topic_scores,
                       color = tests[type]['color'])
              plt.title(topic)
              plt.show()

          if plot_hist:
            if dt_detect == max(dt_detects):
              # Plot histogram of positive and negative values at
              # i_window_start + di_detect and vertical line for test value
              values_pos = [bundle_pos[t].values[di_detect] for t in bundle_pos]
              values_neg = [bundle_neg[t].values[di_detect] for t in bundle_neg]

              n, bins, patches = plt.hist([log(v) for v in values_pos],
                                          bins = 25,
                                          color = (0,0,1),
                                          normed = True)
              plt.hold(True)
              plt.setp(patches, 'facecolor', (0,0,1), 'alpha', 0.25)

              n, bins, patches = plt.hist([log(v) for v in values_neg],
                                          bins = 25,
                                          color = (1,0,0),
                                          normed = True)

              plt.setp(patches, 'facecolor', (1,0,0), 'alpha', 0.25)
              #print 'Test value: ', log(test_val)
              """
              print 'Score: ', detection_func(bundle_pos, bundle_neg,
                                              test_trajectory,
                                              len(test_trajectory) - 1,
                                              cmpr_window)
              """
              plt.axvline(log(test_val), hold = 'on',
                          color = tests[type]['color'], linewidth = 2)
              plt.title(topic)
              plt.hold(False)
              plt.draw()
      scores[type][topic] = Timeseries(topic_score_times, topic_scores)
  results['detection'] = detection
  results['scores'] = scores
  return results

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def detection_func(bundle_pos, bundle_neg, trajectory_test, idx, cmpr_window):
  gamma = 1

  if cmpr_window > 1:
    dists_pos = []
    dists_neg = []

    # Make the min index 1, since we are taking log of values of a cumsum and the
  # value at 0 will be 0.
    imin = max(idx - cmpr_window + 1, 1)
    imax = idx

    if imin == imax:
      return 0

    trajectory_test_cmpr = trajectory_test[imin:imax]

    # Convex distance function. SLOW
    # dist = lambda x, y: abs(log(x) - log(y))

    bundle_pos_cmpr = [ bundle_pos[topic].values[imin:imax] 
                        for topic in bundle_pos ]

    bundle_neg_cmpr = [ bundle_neg[topic].values[imin:imax] 
                        for topic in bundle_neg ]

    dists_pos = [
      np.mean(
        [
          abs(log(trajectory_test_cmpr[i]) - log(trajectory_pos_cmpr[i]))
          for i in range(len(trajectory_pos_cmpr))
        ]
      )
      for trajectory_pos_cmpr in bundle_pos_cmpr
    ]

    dists_neg = [
      np.mean(
        [
          abs(log(trajectory_test_cmpr[i]) - log(trajectory_neg_cmpr[i]))
          for i in range(len(trajectory_neg_cmpr))
        ]
      )
      for trajectory_neg_cmpr in bundle_neg_cmpr
    ]

    prob_pos = np.mean([exp(-gamma * d) for d in dists_pos])
    prob_neg = np.mean([exp(-gamma * d) for d in dists_neg])
  else:
    prob_pos = np.mean( [ exp(-gamma * abs(log(trajectory_test[idx]) - \
                          log(bundle_pos[t].values[idx])))
                          for t in bundle_pos ] )
    prob_neg = np.mean( [ exp(-gamma * abs(log(trajectory_test[idx]) - \
                          log(bundle_neg[t].values[idx])))
                          for t in bundle_neg ] )

  return prob_pos / prob_neg

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def ts_sample_topics(ts_info_orig, p_sample):
  ts_info = {}
  for t in ts_info_orig.keys():
    if np.random.rand() < p_sample:
      ts_info[t] = ts_info_orig[t]
  return ts_info

#=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
def viz_timeseries(ts_infos, normalize = True):
  np.random.seed(2243626)

  plt.ion()
  plt.close('all')
  #colors = [(0,0,1), (1,0,0)]
  colors = ['k', 'k']
  linestyles = ['-', '-']
  linewidths = [1, 1.5]
  labels = ['$\mathcal{R}_+$', '$\mathcal{R}_-$']

  rand_colors = False
  detection_window_time = 2 * 3600 * 1000
  #ts_norm_func = ts_mean_median_norm_func(1, 0)
  ts_norm_func = ts_pnorm_func(p = 1)

  bundles = {}
  w_smooth = 50
  fig = plt.figure()
  for (i, ts_info) in enumerate(ts_infos):
    # Sample
    ts_info = ts_sample_topics(ts_info, 0.025)
    
    """
    color = colors[i]
    for t in ts_info:
      ts = ts_info[t]['ts']
      plt.plot(ts.times, ts.values, color = color)
      plt.hold(True)
      ts_norm = ts_norm_func(ts.values)
      print 'timeseries norm', ts_norm
      plt.plot(ts.times, ts_norm * np.ones(len(ts.times)),
               color = 'k', linewidth = 2)
      raw_input()
      ts_normalized = (np.array(ts.values) + 0.01) / (ts_norm + 0.01)
      #ts_normalized = [max(0, v) for v in np.array(ts.values) - ts_norm]
      plt.plot(ts.times, ts_normalized, color = 'k', linestyle = '--')
      plt.hold(False)
      raw_input()
    """

    # Normalize.
    if normalize:
      ts_info = ts_normalize(ts_info, ts_norm_func, beta = 1)
      
    plot_raw = True
    if plot_raw:
      for t in ts_info:
        if max(ts_info[t]['ts'].values) < 100:
          continue
        times = np.array(ts_info[t]['ts'].times)
        plt.plot((times - np.min(times)) / 3600000.0, ts_info[t]['ts'].values,
                 color = 'k')
        plt.title('Topic: ' + t)
        plt.xlabel('time (hours)')
        plt.ylabel('rate')
        raw_input()

    # Create bundles.
    bundle = ts_bundle(ts_info, detection_window_time, w_smooth = w_smooth)
    bundles[i] = bundle
    # Plot.
    color = colors[i]
    for (ti, t) in enumerate(bundle):
      if rand_colors:
        color = (np.random.rand(), np.random.rand(), np.random.rand())
      label = None
      if ti == 0:
        label = labels[i]
      plt.plot((np.array(bundle[t].times) - bundle[t].tmin) / (3600 * 1000.0),
                   bundle[t].values, hold = 'on', linewidth = linewidths[i],
                   color = color, linestyle = linestyles[i], label = label)
      """
      plt.draw()
      plt.title(t)
      sleep(1)
      """
    plt.draw()
  plt.title('Reference Signals (Transformations: Spikes, Baseline, Log)')
  plt.xlabel('time (hours)')
  plt.ylabel('signal')
  #xplt.legend(loc = 2)

  plot_scatter = False
  if plot_scatter:
    raw_input()
    plt.close(fig)
    fig = plt.figure()
    for i in bundles:
      for topic in bundles[i]:
        ts = bundles[i][topic].values
        consec1 = [ ts[j] for j in range(len(ts) - 1) ]
        consec2 = [ ts[j+1] - ts[j] for j in range(len(ts) - 1) ]
        plt.scatter(consec1, consec2, color = colors[i])
        plt.hold(True)
      plt.draw()

  plot_hist = False
  if plot_hist:
    raw_input()
    plt.close(fig)
    fig = plt.figure()
    for time in np.linspace(0, detection_window_time - 1, 20):
      for i in bundles:
        hist = []
        for topic in bundles[i]:
          ts = bundles[i][topic]
          idx = ts.dtime_to_dindex(time)
          hist.append(ts.values[idx])
        
        n, bins, patches = plt.hist(hist, color = colors[i],
                                    normed = True)
        plt.setp(patches, 'facecolor', colors[i], 'alpha', 0.25)
        plt.hold(True)
      plt.hold(False)
      plt.title(str((detection_window_time - time) / (60 * 1000)) + \
                    ' minutes before onset')
      plt.draw()
      raw_input()

def build_gexf(edges, out_name, p_sample = 1):
  if not Gexf_loaded:
    print 'Could not load Gexf from module gexf.'
    return
  gexf = Gexf("snikolov", out_name)
  graph = gexf.addGraph('directed', 'dynamic', out_name)
  end = str(max([edge[2] for edge in edges]))
  for (src, dst, time) in edges:
    if np.random.rand() > p_sample:
      continue
    # Assumes time is in epoch seconds
    #d = datetime.datetime.fromtimestamp(int(time))    
    #date = d.isoformat()
    start = str(time)
    if not graph.nodeExists(src):
      graph.addNode(id = src, label = '', start = start, end = end)
    if not graph.nodeExists(dst):
      graph.addNode(id = dst, label = '', start = start, end = end)
    graph.addEdge(id = str(src) + ',' + str(dst), source = src,
                  target = dst, start = start, end = end)
  out = open('data/graphs/' + out_name + '.gexf', 'w')
  gexf.write(out)
  out.close()
