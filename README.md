# k_means-mpi
parallel k-means clustering using mpi4py

Project was originally done by[1]. I made my own changes for it to work and perform as required, using dataset[2]. There were some issues getting started with mpi4py and somethings were lost between python2 version so had to install the right dependables [3].

The final result of an output run consists of two text files:
1) output_filename_centroids list for each mean, the number of data points in the cluster and the top 50 most important words of the centroid.
2) output_filename_clusters list the mxm track ids in each cluster.

References:
[1] https://github.com/masenf/mxm_k_means
[2] http://millionsongdataset.com/pages/getting-dataset/
[3] scrapy/scrapy#2115
