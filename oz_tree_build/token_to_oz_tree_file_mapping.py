token_to_file_map = {
    # Base tree for chordates, assuming initial divergence at 550Mya.
    # Note: BASE is not included here as it's passed explicitly as the starting tree


    'AMORPHEA': { 'file': 'Amorphea.PHY', 'edge_length': 50, 'taxon': None },
    'CRUMS': { 'file': 'CRuMs.PHY', 'edge_length': None, 'taxon': None },
    'DIAPHORETICKES': { 'file': 'Diaphoretickes.PHY', 'edge_length': 100, 'taxon': None },
    'METAZOA': { 'file': 'Animals.PHY', 'edge_length': 150, 'taxon': None },
    'PORIFERA': { 'file': 'PoriferaOneZoom.phy', 'edge_length': 50, 'taxon': None },
    'CTENOPHORA': { 'file': 'CtenophoresPoder2001.PHY', 'edge_length': 50, 'taxon': None },
    'AMBULACRARIA': { 'file': 'Ambulacraria.PHY', 'edge_length': 20, 'taxon': 'Ambulacraria' },
    #  DEEPFIN tree root (Shark + bony-fish) is at 462.4. Guess for Cyclostome divergence = 500Mya
    'CYCLOSTOMATA': { 'file': 'Cyclostome_full_guess.PHY', 'edge_length': 43, 'taxon': None },
    'LAMPREYS': { 'file': 'Lampreys_Potter2015.phy', 'edge_length': 332, 'taxon': None },
    'GNATHOSTOMATA': { 'file': 'BonyFishOpenTree.PHY', 'edge_length': 65, 'taxon': None },
    # for fewer species but with dates, try 
    # tree.substitute('GNATHOSTOMATA@', 'BespokeTree/include_files/Deepfin2.phy', 37.6)  # C20=430Ma

    'CHONDRICHTHYES': { 'file': 'Chondrichthyes_Renz2013.phy', 'edge_length': 40, 'taxon': None },
    'HOLOCEPHALI': { 'file': 'Holocephali_Inoue2010.PHY', 'edge_length': 250, 'taxon': None },
    'BATOIDEA': { 'file': 'Batoids_Aschliman2012.PHY', 'edge_length': 100, 'taxon': None },
    # sharks are problematic in OToL v3 & 4, hence lots of files included here
    'SELACHII': { 'file': 'Naylor2012Selachimorpha.PHY', 'edge_length': 75, 'taxon': None },
    'DALATIIDAE': { 'file': 'Naylor2012Dalatiidae.PHY', 'edge_length': 116.1, 'taxon': None },
    'SOMNIOSIDAEOXYNOTIDAE': { 'file': 'Naylor2012Somniosidae_Oxynotidae.PHY', 'edge_length': 110.51, 'taxon': None },
    'ETMOPTERIDAE': { 'file': 'Naylor2012Etmopteridae.phy', 'edge_length': 110.51, 'taxon': None },
    'SQUATINIDAE': { 'file': 'Naylor2012Squatinidae.phy', 'edge_length': 147.59, 'taxon': None },
    'PRISTIOPHORIDAE': { 'file': 'Naylor2012Pristiophoridae.phy', 'edge_length': 147.59, 'taxon': None },
    'SCYLIORHINIDAE3': { 'file': 'Naylor2012Scyliorhinidae3.PHY', 'edge_length': 170, 'taxon': None },
    'SCYLIORHINIDAE2': { 'file': 'Naylor2012Scyliorhinidae2.PHY', 'edge_length': 134.467193, 'taxon': None },
    'CARCHARHINICAE_MINUS': { 'file': 'Naylor2012Carcharhinicae_minus.PHY', 'edge_length': 134.467193, 'taxon': 'Most_Carcharhinicae_' },

    #  Choanoflagellates: http://www.pnas.org/content/105/43/16641.short 

    ##########  NB: to use the original deepfin tree, substitute these text strings back in instead ##########
    # 	tree.substitute('TETRAPODA@', '(Xenopus_tropicalis:335.4,(Monodelphis_domestica:129,(Mus_musculus:71.12,Homo_sapiens:71.12):57.88):206.4)Tetrapodomorpha:46.5');
    # 	tree.substitute('COELACANTHIFORMES@', 'Latimeria_chalumnae:409.4');
    # 	tree.substitute('DIPNOI@', '(Neoceratodus_forsteri:241.804369,(Protopterus_aethiopicus_annectens:103.2,Lepidosiren_paradoxa:103.2):138.604369)Dipnoi:140.095631');
    # 	tree.substitute('POLYPTERIFORMES@', '(Erpetoichthys_calabaricus:29.2,(Polypterus_senegalus:16.555114,Polypterus_ornatipinnis:16.555114):12.644886)Polypteriformes:353.4');
    # 	tree.substitute('ACIPENSERIFORMES@', '(Polyodon_spathula:138.9,(Acipenser_fulvescens:38.592824,(Scaphirhynchus_platorynchus:19.382705,Scaphirhynchus_albus:19.382705):19.210119):100.307176)Acipenseriformes:211.2');


    'COELACANTHIFORMES': { 'file': 'CoelacanthSudarto2010.phy', 'edge_length': 414, 'taxon': None },
    'DIPNOI': { 'file': 'LungfishCriswell2011.phy', 'edge_length': 138, 'taxon': None },
    'POLYPTERIFORMES': { 'file': 'BicherSuzuki2010.phy',      'edge_length': 353.4, 'taxon': 'Polypteriformes' },
    'ACIPENSERIFORMES': { 'file': 'SturgeonKrieger2008.phy',   'edge_length': 166.1, 'taxon': 'Acipenseriformes' },
    'HOLOSTEI': { 'file': 'GarsDeepfin.phy', 'edge_length': 54.6, 'taxon': 'Holostei' },

    ########## TETRAPODS  ###########
    #  C18 @ 415, ChangedOneZoom tetrapods root @ 340 Mya. Stem = 75Ma
    'TETRAPODA': { 'file': 'Tetrapods_Zheng_base.PHY', 'edge_length': 75, 'taxon': None },
    # $tree.substitute('AMPHIBIA@',     'BespokeTree/include_files/AmphibiansOneZoom.phy',                30.0);
    'AMPHIBIA': { 'file': 'AmphibiansOpenTree.PHY', 'edge_length': 30, 'taxon': None },
    'CROCODYLIA': { 'file': 'Crocodylia_OneZoom.phy', 'edge_length': 152.86, 'taxon': None },
    'TESTUDINES': { 'file': 'Testudines_OneZoom.phy', 'edge_length': 55.77, 'taxon': None },
    'NEOGNATHAE': { 'file': 'Neognathae_minus_passerines_OneZoom.PHY', 'edge_length': 15.69, 'taxon': None },
    'PALAEOGNATHAE': { 'file': 'PalaeognathaeMitchell2014.PHY', 'edge_length': 40.45, 'taxon': None },
    'TINAMIFORMES': { 'file': 'Tinamous_OneZoom.phy', 'edge_length': 6.85, 'taxon': None },
    'PASSERIFORMES': { 'file': 'PasserinesOneZoom.phy', 'edge_length': 8, 'taxon': None },
    'GALAPAGOS_FINCHES_AND_ALLIES_': { 'file': 'GalapagosFinchesLamichhaney2015.phy', 'edge_length': 3.6, 'taxon': None },

    # for original onezoom tree use 
    # tree.substitute('EUTHERIA@',          'BespokeTree/include_files/PlacentalsOneZoom.phy');
    'MAMMALIA': { 'file': 'Mammal_base.phy', 'edge_length': 140, 'taxon': None },
    'MARSUPIALIA': { 'file': 'Marsupial_recalibrated.phy', 'edge_length': 73, 'taxon': None },
    'EUTHERIA': { 'file': 'PlacentalsPoulakakis2010.phy', 'edge_length': 70, 'taxon': None },
    'BOREOEUTHERIA': { 'file': 'BoreoeutheriaOneZoom_altered.phy', 'edge_length': 5, 'taxon': None },
    'XENARTHRA': { 'file': 'XenarthraOneZoom.phy', 'edge_length': 17.8, 'taxon': None },
    'AFROTHERIA': { 'file': 'AfrotheriaPoulakakis2010.phy', 'edge_length': 4.9, 'taxon': None },


    ########## (to use original OneZoom data, try ###############
    ##########	tree.substitute('PRIMATES@', 'BespokeTree/include_files/PrimatesOneZoom.phy', 23.3); #######

    #  Onezoom colugo-primate @ 90 Mya, Springer primates root @ 66.7065Mya. Here stem = 90 - 66.7065 = 23.3My
    #  But ancestor's tale colugo-primate @ 70 Ma

    # tree.substitute('PRIMATES@',      'BespokeTree/include_files/PrimatesSpringer2012.phy',  2.2932);  # base = 66.7068 C9 @ 69
    'PRIMATES': { 'file': 'PrimatesSpringer2012_AT.PHY', 'edge_length': 5, 'taxon': None },
    'HYLOBATIDAE': { 'file': 'GibbonsCarbone2014.phy', 'edge_length': 12.6, 'taxon': None },
    'DERMOPTERA': { 'file': 'DermopteraJanecka2008.phy', 'edge_length': 55, 'taxon': None },

    # STURGEON_TREE from http://onlinelibrary.wiley.com/doi/10.1111/j.1439-0426.2008.01088.x/abstract - should contain approx 30 spp. Base is at 

    # Needed
    # Correct Rattite tree
    # SHARK_TREE??
    # AMPHIOXUS_TREE_~32SPP - 24 Branchiostoma species, 7 Asymmetron species, 1 Epigonichthys (http://eolspecies.lifedesks.org/pages/63233) see http://www.bioone.org/doi/abs/10.2108/zsj.21.203

    # Tunicate tree ~ 2,150 spp - see T. Stuck for phylogeny

    # for dating look at B. Misof, et al. 2014. Phylogenomics resolves the timing and pattern of insect evolution. Science 346 (6210): 763-767.
    'PROTOSTOMIA': { 'file': 'Protostomes.PHY', 'edge_length': 50, 'taxon': None },
    'HOLOMYCOTA': { 'file': 'Holomycota.PHY', 'edge_length': 300, 'taxon': None },
    'APHELIDA': { 'file': 'Aphelida_rough.PHY', 'edge_length': 100, 'taxon': None  }
}
