import matplotlib.pyplot as plt
import matplotlib as mpl
from cycler import cycler
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplcursors
import math
import tkinter as tk
import numpy as np
from tkinter import Frame

def graphs_set_dark_mode():
    plt.style.use("dark_background")
    mpl.rcParams['axes.prop_cycle'] = cycler(color=['#ffd500'])
    mpl.rcParams['figure.facecolor'] = "#333333"
    mpl.rcParams['axes.facecolor'] = "#333333"

def graphs_set_light_mode():
    plt.style.use("default")

class Graph(Frame):
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        self.x = np.arange(0, 1, 1.0)
        self.y = np.arange(0, 1, 1.0)
        self.xscale = 1
        self.yscale = 1
        self.line, = self.ax.plot(self.x, self.y, marker="o")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.grabbed_point = False
        self.index = 0
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.canvas.mpl_connect('button_press_event', self.onclick)
        self.canvas.mpl_connect('button_release_event', self.onrelease)
        self.canvas.mpl_connect('motion_notify_event', self.onmove)
        self.margin = 0.2
        self.ax.grid()
        self.fig.canvas.draw()
        
    def set_xlabel(self, label):
        self.ax.set_xlabel(label)
        
    def set_ylabel(self, label):
        self.ax.set_ylabel(label)
        
    def set_title(self, title):
        self.ax.set_title(title)
        
    def set_data(self, xdata, ydata):
        self.x = xdata
        self.y = ydata
        axis_min = min(xdata)
        axis_max = max(xdata)
        self.xscale = (axis_max-axis_min)
        if self.xscale == 0:
            self.xscale = 1
        self.ax.set_xlim(axis_min-(self.xscale*self.margin), axis_max+(self.xscale*self.margin))
        axis_min = min(ydata)
        axis_max = max(ydata)
        self.yscale = (axis_max-axis_min)
        if self.yscale == 0:
            self.yscale = 1
        self.ax.set_ylim(axis_min-(self.yscale*self.margin), axis_max+(self.yscale*self.margin))
        self.line.set_xdata(self.x)
        self.line.set_ydata(self.y)
        self.fig.canvas.draw()
        
    def get_data(self):
        return (self.x, self.y)
        
    def onclick(self, event):
        min_distance = 999999999999
        for i, point in enumerate(self.x):
            distance = math.sqrt(abs(point-event.xdata)**2/self.xscale + abs(self.y[i]-event.ydata)**2/self.yscale)
            if distance < min_distance:
                min_distance = distance
                self.index = i
        if event.button == mpl.backend_bases.MouseButton.LEFT:
            if min_distance < 0.5:
                self.grabbed_point = True
            else:
                for i, point in enumerate(self.x):
                    if event.xdata > point:
                        self.index = i
                self.x = np.insert(self.x, self.index+1, event.xdata)
                self.y = np.insert(self.y, self.index+1, event.ydata)
                self.line.set_xdata(self.x)
                self.line.set_ydata(self.y)
                self.fig.canvas.draw()
        elif event.button == mpl.backend_bases.MouseButton.RIGHT:
            if min_distance < 0.5:
                self.x = np.delete(self.x, self.index)
                self.y = np.delete(self.y, self.index)
                self.line.set_xdata(self.x)
                self.line.set_ydata(self.y)
                self.fig.canvas.draw()
        
    def onrelease(self, event):
        self.grabbed_point = False
        axis_min = min(self.x)
        axis_max = max(self.x)
        self.xscale = (axis_max-axis_min)
        if self.xscale == 0:
            self.xscale = 1
        self.ax.set_xlim(axis_min-(self.xscale*self.margin), axis_max+(self.xscale*self.margin))
        axis_min = min(self.y)
        axis_max = max(self.y)
        self.yscale = (axis_max-axis_min)
        if self.yscale == 0:
            self.yscale = 1
        self.ax.set_ylim(axis_min-(self.yscale*self.margin), axis_max+(self.yscale*self.margin))
        self.fig.canvas.draw()
        
    def onmove(self, event):
        if self.grabbed_point:
            self.x[self.index] = event.xdata
            self.y[self.index] = event.ydata
            self.line.set_xdata(self.x)
            self.line.set_ydata(self.y)
            self.fig.canvas.draw()