# -*- coding: utf-8 -*-
"""
Created on Sun Apr 25 14:42:31 2021

@author: Usuario
"""

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import os 
import snappy 
from snappy import Product 
from snappy import ProductIO
from snappy import WKTReader 
from snappy import HashMap 
from snappy import GPF
import shapefile
import pygeoif
#TKINTER
import tkinter as tk
from tkinter import filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

archivo_imagen = ""
archivo_shape = ""
product = None
product_calibrated = None
flood_mask = None
#Inicialización de la ventana
root = tk.Tk()
root.title("Examen unidad 2")
root.geometry("670x800")
root.configure(bg="blue")

####LEER LOS DATOS DE LA IMAGEN
def cargarImagen():
    global product
    #Cargar imagenes
    path_to_sentinel_data = archivo_imagen
    product = ProductIO.readProduct(path_to_sentinel_data)
    
    #Leer y mostrar la informaciónd de la imagen
    width = product.getSceneRasterWidth()
    print("Width: {} px".format(width))
    height = product.getSceneRasterHeight()
    print("Height: {} px".format(height))
    name = product.getName()
    print("Name: {}".format(name))
    band_names = product.getBandNames()
    print("Band names: {}".format(", ".join(band_names)))
    print("IMAGEN CARGADA EXITOSAMENTE")
##Crear una funcion para mostrar el producto en una
def plotBand(product, band, vmin, vmax):
    global root
    band = product.getBand(band)
    w = band.getRasterWidth()
    h = band.getRasterHeight()
    print(w, h)
    band_data = np.zeros(w * h, np.float32)
    band.readPixels(0, 0, w, h, band_data)
    band_data.shape = h, w
    width = 12
    height = 12
    fig = plt.figure(figsize=(width, height))
    mapa = FigureCanvasTkAgg(fig, master=root)
    mapa.get_tk_widget().place( x = 10, y = 200 )
    imgplot = plt.imshow(band_data, cmap=plt.cm.binary, vmin=vmin, vmax=vmax)
    return imgplot

##PRE-PROCESAMIENTO
def preprocesado():
    ##Aplicar correccion orbital
    global product
    global product_calibrated
    global HashMap
    print(product)
    parameters = HashMap()
    GPF.getDefaultInstance().getOperatorSpiRegistry().loadOperatorSpis()
    parameters.put('orbitType', 'Sentinel Precise (Auto Download)')
    parameters.put('polyDegree', '3')
    parameters.put('continueOnFail', 'false')
    apply_orbit_file = GPF.createProduct('Apply-Orbit-File', parameters, product)
    
    ##Recortar la imagen
    r = shapefile.Reader(archivo_shape)
    g=[]
    for s in r.shapes():
        g.append(pygeoif.geometry.as_shape(s))
    m = pygeoif.MultiPoint(g)
    wkt = str(m.wkt).replace("MULTIPOINT", "POLYGON(") + ")"
    
    #Usar el shapefile para cortar la imagen
    SubsetOp = snappy.jpy.get_type('org.esa.snap.core.gpf.common.SubsetOp')
    bounding_wkt = wkt
    geometry = WKTReader().read(bounding_wkt)
    HashMap = snappy.jpy.get_type('java.util.HashMap')
    GPF.getDefaultInstance().getOperatorSpiRegistry().loadOperatorSpis()
    parameters = HashMap()
    parameters.put('copyMetadata', True)
    parameters.put('geoRegion', geometry)
    product_subset = snappy.GPF.createProduct('Subset', parameters, apply_orbit_file)
    
    #Mostrar las dimensiones de la imagen
    width = product_subset.getSceneRasterWidth()
    print("Width: {} px".format(width))
    height = product_subset.getSceneRasterHeight()
    print("Height: {} px".format(height))
    band_names = product_subset.getBandNames()
    print("Band names: {}".format(", ".join(band_names)))
    band = product_subset.getBand(band_names[0])
    print(band.getRasterSize())
    #plotBand(product_subset, "Intensity_VV", 0, 100000)
    
    ##Aplicar la calibracion de la imagen
    parameters = HashMap()
    parameters.put('outputSigmaBand', True)
    parameters.put('sourceBands', 'Intensity_VV')
    parameters.put('selectedPolarisations', "VV")
    parameters.put('outputImageScaleInDb', False)
    product_calibrated = GPF.createProduct("Calibration", parameters, product_subset)
    #plotBand(product_calibrated, "Sigma0_VV", 0, 1)
    print("PREPROCESAMIENTO HECHO EXITOSAMENTE")
def aplicarFiltro(var_umbral):
    global root
    global flood_mask
    ##Aplicar el FILTRO Speckle
    filterSizeY = '5'
    filterSizeX = '5'
    parameters = HashMap()
    parameters.put('sourceBands', 'Sigma0_VV')
    parameters.put('filter', 'Lee')
    parameters.put('filterSizeX', filterSizeX)
    parameters.put('filterSizeY', filterSizeY)
    parameters.put('dampingFactor', '2')
    parameters.put('estimateENL', 'true')
    parameters.put('enl', '1.0')
    parameters.put('numLooksStr', '1')
    parameters.put('targetWindowSizeStr', '3x3')
    parameters.put('sigmaStr', '0.9')
    parameters.put('anSize', '50')
    speckle_filter = snappy.GPF.createProduct('Speckle-Filter', parameters, product_calibrated)
    #plotBand(speckle_filter, 'Sigma0_VV', 0, 1)
    
    ##Aplicar la correccion del terremo
    parameters = HashMap()
    parameters.put('demName', 'SRTM 3Sec')
    parameters.put('pixelSpacingInMeter', 10.0)
    parameters.put('sourceBands', 'Sigma0_VV')
    speckle_filter_tc = GPF.createProduct("Terrain-Correction", parameters, speckle_filter)
    plotBand(speckle_filter_tc, 'Sigma0_VV', 0, 0.1)
    
    #Crear una mascara binaria para la inundacion
    parameters = HashMap()
    BandDescriptor = snappy.jpy.get_type('org.esa.snap.core.gpf.common.BandMathsOp$BandDescriptor')
    targetBand = BandDescriptor()
    targetBand.name = 'Sigma0_VV_Flooded'
    targetBand.type = 'uint8'
    targetBand.expression = '(Sigma0_VV < ' + var_umbral + ') ? 1 : 0'
    targetBands = snappy.jpy.array('org.esa.snap.core.gpf.common.BandMathsOp$BandDescriptor', 1)
    targetBands[0] = targetBand
    parameters.put('targetBands', targetBands)
    flood_mask = GPF.createProduct('BandMaths', parameters, speckle_filter_tc)
    plotBand(flood_mask, 'Sigma0_VV_Flooded', 0, 1)
    print("FILTRO APLICADO EXITOSAMENTE")
    
def guardarArchivo():
    global flood_mask
    #Crear la imagen a partir de la mascara
    ProductIO.writeProduct(flood_mask, "C:/Users/Usuario/Desktop/Actvidades_CTE_334/Examen_unidad_2/final_mask", 'GeoTIFF')
    print("IMAGEN CREADA EXITOSAMENTE A PARTIR DE MASCARA")


#StringVar: Variables de control, que asocian widget para almancenar valores
imagen = tk.StringVar()
shapeFile = tk.StringVar()
tk_umbral = tk.StringVar()
#Variables globales
#marginX = 10
#entryWidth = 500
#Funciones
def obtenerImagen():
    global archivo_imagen
    archivo_imagen = filedialog.askopenfilename(initialdir = "/",title = "Select file",filetypes = (("zip files","*.zip"),("all files","*.*")))
    imagen.set(archivo_imagen)
    cargarImagen()
def obtenerShapeFile():
    global archivo_shape
    archivo_shape = filedialog.askopenfilename(initialdir = "/",title = "Select file",filetypes = (("shape files","*.shp"),("all files","*.*")))
    shapeFile.set(archivo_shape)
def aplicarMascara():
    #1.57E-2
    var_umbral = tk_umbral.get()
    aplicarFiltro(var_umbral)
#UI
#UI_IMAGEN
butonImagen = tk.Button(root, text="Seleccionar una imagen",command=obtenerImagen)
butonImagen.pack()
entradaImagen = tk.Entry(root, textvariable=imagen)
entradaImagen.pack()
#UI_SHAPEFILE
butonShape = tk.Button(root, text="Seleccionar una shapefile",command=obtenerShapeFile)
butonShape.pack()
entradaShape = tk.Entry(root, textvariable=shapeFile)
entradaShape.pack()
#UI_PREPROCESAR LA IMAGEN
butonPreProcesar = tk.Button(root, text="Preprocesar imagen",command=preprocesado)
butonPreProcesar.pack()
#UI_UMBLRAL
etiquetaUmbral = tk.Label(root, text="Defina el umbral: ")
etiquetaUmbral.pack()
entradaUmbral = tk.Entry(root, textvariable=tk_umbral)
entradaUmbral.pack()
#UI_AplicarMascara
butonAplicarMascara = tk.Button(root, text="Aplicar mascara",command=aplicarMascara)
butonAplicarMascara.pack()
#UI_CrearArchivo
butonCrearArchivo = tk.Button(root, text="Crear Archivo",command=guardarArchivo)
butonCrearArchivo.pack()

root.mainloop()