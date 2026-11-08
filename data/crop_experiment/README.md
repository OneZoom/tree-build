# Crop experiment

An experiment to test different methods of finding a square crop on species images.
Also contains a tool for labelling ground truth ideal crops and visualising results in the 'labeller' dir.

To run:

```bash
dvc pull  # to download the datasets
# run whichever cropper you're interested in...
venv/bin/python data/crop_experiment/run_cropper.py "jev-two-phase"
venv/bin/python data/crop_experiment/labeller/server.py
# # view the results by opening http://127.0.0.1:8765
```

## Notes

- There's no unambiguous 'best square crop' for an image. Some of the ground truth crops make arbitrary
  decisions. As such, no approach is going to reach 100% with the current metric.
- Azure's smart crop isn't much better than a naive centre crop.
- smartcrop.py, which works by looking for edges and skin tones, was rubbish for this.
- Most of the cropper implementations don't try to change the size of the crop,
  they keep it as large of a square as will fit and are just trying to decide where along the long edge to place it. I've not played a lot with trying to fit tighter boxes, naive experimentation made results worse because the labelled ground truth largely stays zoomed out.
- I was kind of aiming for a cost of around $10 per 300k images, since that's how many images we have and that's an affordable number.
