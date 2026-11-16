# SGeMS Workbench 0.4.4
Install the ZIP in QGIS 3.34–3.x using Plugins → Manage and Install Plugins → Install from ZIP. Enable SGeMS Workbench and open the Processing Toolbox. Search for “Export point set to SGeMS”.

Choose a projected point layer and one or more numeric measurements. To export a subset, use the input selector’s selected features option. Each multipoint part receives the feature’s attributes. Text fields are excluded. The exported file contains no CRS definition. Record the layer CRS, units and vertical datum alongside your model.

Use 2D for map samples. Choose Geometry Z for surveyed 3D locations, or Elevation field for sample-level elevations. For vertical boreholes with positive depths below collar, midpoint elevation = collar elevation − (from depth + to depth)/2. Deviated holes require sample XYZ along the surveyed trajectory. The exporter expects one point per sample and does no compositing.

Save the .dat file. In SGeMS select Objects → Load Object, choose the file, select Point Set, assign X/Y/Z to columns 1/2/3 and enable the no-data value -99999. Verify point count and properties. Null property values use this sentinel. Missing coordinates stop export.

License: GPL-2.0-or-later.

Open Plugins → SGeMS → SGeMS workbench. On Linux, Applications → Launch SGeMS looks for a native executable called sgems or s-gems. Use Locate native SGeMS to pick bin/linux/sgems or bin/linux/s-gems from a Linux build. The workbench sets the build's resource and library paths for the child process and opens the SGeMS desktop window. The ZIP contains the QGIS launcher only. Linux build instructions are linked in Applications. On Windows use the installer controls and locate sgems.exe after setup.

On Sample points export a QGIS point layer or open an existing point set from this exporter. Drag to rotate the embedded Matplotlib preview. Select a numeric property to change colours. Grey means missing. For a local engineering grid choose Use stored local model XY only when the coordinates use compatible linear units. Save and open in ParaView writes the complete XYZ and all measurements as .vtp. The 3D viewer displays sample points; ordinary kriging is available within the workbench on x86-64 Linux.

## Standalone kriging on Intel/AMD 64-bit Linux
Open a point set and choose a measured property → Ordinary kriging → Run selected algorithm. Set the spherical range and grid dimensions, then save the output. The suggested range is one third of the longest axis span; choose a range justified by the data. Nodes cover the rectangular sample bounding box. Z is a spatial coordinate. For a contact elevation surface from boreholes, export XY with 2D (Z = 0) and select contact elevation as the measured property. For a subsurface volume use sample elevation for Z and a separate measured property. The result is a grid of point estimates. Variance uses a unit sill and zero nugget. It is in normalized units. ParaView is optional.

This product includes software developed by Stanford University and its contributors.
The package includes the GsTL ordinary kriging solver, with source and notices in engine. This is a subset of the modelling functionality. Opening the original SGeMS desktop and running its other algorithms requires a separate runtime.

Source: https://github.com/gerwathome/GsTL at 64318f5337e11d436c4694b147c8ace374ea1176. Build from the engine directory with g++ -O2 -std=gnu++11 -fpermissive -static -s -I. ordinary.cpp -o ordinary-linux-x86_64. Users of the packaged Linux build do not need a compiler.

## Conditional simulations
Choose SGSIM for continuous observations or categorical SISIM for integer facies codes. Set the spherical covariance range, grid dimensions, seed and number of realizations. Each realization is a separate property in the output point set. Use the property dropdown to switch between them.

These workflows use the GsTL sequential simulation driver and simple kriging weights, an isotropic model with zero nugget, and a random node path. The search uses at most 16 informed neighbours within the range. Previously simulated nodes condition later nodes. Data at coincident grid nodes are honoured. In SGSIM, ties share an empirical normal score, and the back-transform clamps the tails at the observed extremes. SISIM uses observed proportions, one shared covariance for the indicators, clamps conditional probabilities and normalizes them before sampling. Off-grid observations participate at their stored coordinates.

The standalone interface covers ordinary kriging and these two simulation workflows. Other standard algorithms and desktop parameter variants are pending. Simulation uses the original GsTL driver with a workbench neighbourhood, RNG and conditional distribution adapter. Reproducibility applies within this bundled build. To rebuild the simulation worker use the ordinary worker command with -std=gnu++14, simulate.cpp and output simulate-linux-x86_64. The bundled GsTL driver omits unused sampling overloads and the matrix solver header adds forward declarations for current compilers.

## Send SGeMS data to QGIS or ParaView

In the SGeMS desktop, save the object in ASCII GSLIB format. In Workbench choose **Open point set** and confirm the X, Y and Z columns and the missing-value code. All other columns become properties. Choose **Open Cartesian grid** for a property-only regular, axis-aligned grid. Enter the original node counts, first cell centre, spacing and missing value. GSLIB rows advance first in X, then Y, then Z.

Choose **Add to QGIS map** to create a temporary PointZ layer with every property and realization. The QGIS export workflow carries the source CRS through the model in the same session. For files opened from disk, select the original CRS or choose No projection for a local grid. Use **Make Permanent** to keep the layer in a GeoPackage. **Save and open in ParaView** writes the same XYZ nodes and properties as VTK PolyData (.vtp). Grid transfer produces cell-centre points. Native binary projects, rotated grids and masked grids require conversion first.
