"""DICOM import / export: CT series, RT Structure Set, RT Plan (beam geometry) and RT Dose.

Everything is read locally. Patient identifiers are replaced by an anonymous code on import, so the
program never shows or stores names, IDs or birth dates. Requires pydicom.
"""
from __future__ import annotations

import datetime
import hashlib
import os
from dataclasses import dataclass, field

import numpy as np

from .image import Image3D
from .structures import StructureSet


@dataclass
class SeriesInfo:
    modality: str
    uid: str
    files: list = field(default_factory=list)
    description: str = ""
    patient_code: str = ""
    frame_uid: str = ""
    referenced: str = ""       # referenced series / frame (for RTSTRUCT)

    def label(self):
        n = len(self.files)
        return f"{self.modality} · {self.description or '(no description)'} · {n} file{'s' if n != 1 else ''}"


def _pydicom():
    try:
        import pydicom
        return pydicom
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pydicom is not installed (pip install pydicom)") from e


def anon_code(ds) -> str:
    """Stable anonymous code from the patient ID (the ID itself is never kept)."""
    pid = str(getattr(ds, "PatientID", "")) + str(getattr(ds, "PatientName", ""))
    return "ANON-" + hashlib.sha256(pid.encode("utf-8")).hexdigest()[:8].upper() if pid else "ANON"


def scan_folder(folder: str, progress=None) -> list[SeriesInfo]:
    """Find DICOM series in a folder (recursively). Returns CT / RTSTRUCT / RTPLAN / RTDOSE series."""
    pydicom = _pydicom()
    found: dict[str, SeriesInfo] = {}
    paths = [os.path.join(r, f) for r, _, fs in os.walk(folder) for f in fs]
    for n, p in enumerate(paths):
        if progress and n % 50 == 0:
            progress(n, len(paths))
        try:
            ds = pydicom.dcmread(p, stop_before_pixels=True, force=True)
        except Exception:
            continue
        mod = str(getattr(ds, "Modality", ""))
        if mod not in ("CT", "RTSTRUCT", "RTPLAN", "RTDOSE"):
            continue
        uid = str(getattr(ds, "SeriesInstanceUID", p))
        s = found.setdefault(uid, SeriesInfo(mod, uid, [], str(getattr(ds, "SeriesDescription", "")), anon_code(ds),
                                             str(getattr(ds, "FrameOfReferenceUID", ""))))
        s.files.append(p)
        if mod == "RTSTRUCT" and not s.frame_uid:
            try:
                s.frame_uid = str(ds.ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID)
            except Exception:
                pass
    order = {"CT": 0, "RTSTRUCT": 1, "RTPLAN": 2, "RTDOSE": 3}
    return sorted(found.values(), key=lambda s: (order[s.modality], s.description))


def load_ct(files: list[str], max_voxels=40e6, progress=None) -> Image3D:
    """Load a CT series. Oblique series are refused; very large series are resampled."""
    pydicom = _pydicom()
    slices = []
    for n, p in enumerate(files):
        ds = pydicom.dcmread(p, force=True)
        if not hasattr(ds, "ImagePositionPatient"):
            continue
        slices.append(ds)
        if progress and n % 20 == 0:
            progress(n, len(files))
    if not slices:
        raise ValueError("No CT images with positions in this series")
    iop = np.array(slices[0].ImageOrientationPatient, float)
    if not (np.allclose(np.abs(iop), [1, 0, 0, 0, 1, 0], atol=1e-3)):
        raise ValueError("Oblique CT series are not supported (ImageOrientationPatient is not axial)")
    slices.sort(key=lambda d: float(d.ImagePositionPatient[2]))
    zs = np.array([float(d.ImagePositionPatient[2]) for d in slices])
    dz = float(np.median(np.diff(zs))) if len(zs) > 1 else float(getattr(slices[0], "SliceThickness", 3.0))
    ps = [float(v) for v in slices[0].PixelSpacing]          # [row spacing (y), column spacing (x)]
    arr = np.empty((len(slices), int(slices[0].Rows), int(slices[0].Columns)), np.float32)
    for k, d in enumerate(slices):
        a = d.pixel_array.astype(np.float32) * float(getattr(d, "RescaleSlope", 1)) + float(getattr(d, "RescaleIntercept", 0))
        arr[k] = a
    # flipped row / column directions (iop = -1) are turned back to +x / +y
    x0, y0 = float(slices[0].ImagePositionPatient[0]), float(slices[0].ImagePositionPatient[1])
    if iop[0] < 0:
        arr = arr[:, :, ::-1]; x0 = x0 - ps[1] * (arr.shape[2] - 1)
    if iop[4] < 0:
        arr = arr[:, ::-1, :]; y0 = y0 - ps[0] * (arr.shape[1] - 1)
    ds0 = slices[0]
    img = Image3D(np.ascontiguousarray(arr), (ps[1], ps[0], dz), (x0, y0, float(zs[0])),
                  {"name": anon_code(ds0), "id": anon_code(ds0), "description": str(getattr(ds0, "StudyDescription", "")),
                   "frame_uid": str(getattr(ds0, "FrameOfReferenceUID", ""))},
                  str(getattr(ds0, "PatientPosition", "HFS")) or "HFS")
    if arr.size > max_voxels:
        f = (arr.size / max_voxels) ** (1 / 3)
        img = img.resampled(tuple(s * f for s in img.spacing))
    return img


def load_rtstruct(path: str, ss: StructureSet, progress=None) -> list[str]:
    """Add the ROIs of an RT Structure Set to ss (rasterised on the CT grid). Returns the names added."""
    pydicom = _pydicom()
    ds = pydicom.dcmread(path, force=True)
    names = {int(r.ROINumber): str(r.ROIName) for r in getattr(ds, "StructureSetROISequence", [])}
    types = {}
    for o in getattr(ds, "RTROIObservationsSequence", []):
        types[int(o.ReferencedROINumber)] = str(getattr(o, "RTROIInterpretedType", "") or "ORGAN")
    added = []
    seqs = list(getattr(ds, "ROIContourSequence", []))
    for n, rc in enumerate(seqs):
        num = int(rc.ReferencedROINumber)
        name = names.get(num, f"ROI_{num}")
        polys: dict[float, list] = {}
        for c in getattr(rc, "ContourSequence", []):
            if str(getattr(c, "ContourGeometricType", "CLOSED_PLANAR")) not in ("CLOSED_PLANAR", ""):
                continue
            pts = np.array(c.ContourData, float).reshape(-1, 3)
            polys.setdefault(round(float(pts[0, 2]), 2), []).append(pts[:, :2])
        if not polys:
            continue
        mask = ss.rasterise(polys)
        color = tuple(int(v) for v in getattr(rc, "ROIDisplayColor", [255, 255, 0]))
        nm, i = name, 2
        while ss.get(nm):
            nm, i = f"{name}_{i}", i + 1
        ss.add(nm, mask, color, types.get(num, "ORGAN").upper() or "ORGAN")
        added.append(nm)
        if progress:
            progress(n + 1, len(seqs))
    # body first, as in planning systems
    ss.structures.sort(key=lambda s: 0 if s.type == "EXTERNAL" else 1)
    return added


def load_rtdose(path: str):
    """RT Dose as (array Gy [k, j, i], spacing, origin). Axis-aligned grids only."""
    pydicom = _pydicom()
    ds = pydicom.dcmread(path, force=True)
    arr = ds.pixel_array.astype(np.float32) * float(ds.DoseGridScaling)
    if arr.ndim == 2:
        arr = arr[None]
    off = np.array(getattr(ds, "GridFrameOffsetVector", [0]), float)
    ipp = np.array(ds.ImagePositionPatient, float)
    ps = [float(v) for v in ds.PixelSpacing]
    dz = float(np.median(np.diff(off))) if len(off) > 1 else 1.0
    if dz < 0:
        arr, off, dz = arr[::-1], off[::-1], -dz
    return arr, (ps[1], ps[0], dz), (ipp[0], ipp[1], ipp[2] + off[0])


def save_rtstruct(path: str, ss: StructureSet, step=1):
    """Write the structure set as an RT Structure Set (contours from the masks). For teaching only."""
    pydicom = _pydicom()
    from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.3"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    now = datetime.datetime.now()
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTSTRUCT"; ds.PatientName = ss.image.patient.get("name", "ANON"); ds.PatientID = ss.image.patient.get("id", "ANON")
    ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
    ds.StructureSetLabel = "PyTPS"; ds.StructureSetDate = now.strftime("%Y%m%d"); ds.StructureSetTime = now.strftime("%H%M%S")
    ds.SeriesDescription = "PyTPS structures (educational)"; ds.Manufacturer = "PyTPS (educational, not for clinical use)"
    frame = ss.image.patient.get("frame_uid") or generate_uid()
    rf = Dataset(); rf.FrameOfReferenceUID = frame; ds.ReferencedFrameOfReferenceSequence = [rf]
    ds.StructureSetROISequence, ds.ROIContourSequence, ds.RTROIObservationsSequence = [], [], []
    zs = ss.image.axis("z")
    for n, s in enumerate(ss.structures, start=1):
        r = Dataset(); r.ROINumber = n; r.ReferencedFrameOfReferenceUID = frame; r.ROIName = s.name; r.ROIGenerationAlgorithm = "MANUAL"
        ds.StructureSetROISequence.append(r)
        rc = Dataset(); rc.ReferencedROINumber = n; rc.ROIDisplayColor = list(s.color); rc.ContourSequence = []
        for k in np.where(s.mask.any(axis=(1, 2)))[0][::step]:
            for c in ss.contours(s.name, "axial", int(k)):
                cd = Dataset(); cd.ContourGeometricType = "CLOSED_PLANAR"
                pts = np.column_stack([c, np.full(len(c), zs[k])])
                cd.NumberOfContourPoints = len(pts); cd.ContourData = [f"{v:.2f}" for v in pts.ravel()]
                rc.ContourSequence.append(cd)
        ds.ROIContourSequence.append(rc)
        o = Dataset(); o.ObservationNumber = n; o.ReferencedROINumber = n; o.RTROIInterpretedType = s.type; o.ROIInterpreter = ""
        ds.RTROIObservationsSequence.append(o)
    ds.save_as(path, enforce_file_format=True) if "enforce_file_format" in ds.save_as.__code__.co_varnames else ds.save_as(path, write_like_original=False)


def write_ct_series(folder: str, img: Image3D):
    """Write an Image3D as a CT series (used to make test data and teaching datasets from phantoms)."""
    pydicom = _pydicom()
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    os.makedirs(folder, exist_ok=True)
    study, series, frame = generate_uid(), generate_uid(), generate_uid()
    img.patient["frame_uid"] = frame
    for k in range(img.shape[0]):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"; meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        p = os.path.join(folder, f"CT_{k:04d}.dcm")
        ds = FileDataset(p, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
        ds.Modality = "CT"; ds.PatientName = "PHANTOM"; ds.PatientID = img.patient.get("id", "PHANTOM"); ds.PatientPosition = img.orientation
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, series, frame
        ds.SeriesDescription = img.patient.get("description", "phantom")[:64]
        ds.ImagePositionPatient = [f"{img.origin[0]:.3f}", f"{img.origin[1]:.3f}", f"{img.origin[2] + k * img.spacing[2]:.3f}"]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [f"{img.spacing[1]:.4f}", f"{img.spacing[0]:.4f}"]; ds.SliceThickness = f"{img.spacing[2]:.3f}"
        ds.Rows, ds.Columns = img.shape[1], img.shape[2]
        ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = "MONOCHROME2"; ds.BitsAllocated = 16; ds.BitsStored = 16
        ds.HighBit = 15; ds.PixelRepresentation = 1; ds.RescaleIntercept = 0; ds.RescaleSlope = 1
        ds.PixelData = np.round(img.array[k]).astype(np.int16).tobytes()
        ds.save_as(p, enforce_file_format=True) if "enforce_file_format" in ds.save_as.__code__.co_varnames else ds.save_as(p, write_like_original=False)
