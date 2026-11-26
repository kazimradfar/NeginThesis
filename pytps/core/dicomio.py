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


def _base_ds(path, sop_class, modality, img, desc):
    pydicom = _pydicom()
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class; meta.MediaStorageSOPInstanceUID = generate_uid(); meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, meta.MediaStorageSOPInstanceUID
    ds.Modality = modality
    ds.PatientName = img.patient.get("name", "ANON"); ds.PatientID = img.patient.get("id", "ANON")
    ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
    ds.FrameOfReferenceUID = img.patient.get("frame_uid") or generate_uid()
    ds.SeriesDescription = desc
    ds.Manufacturer = "PyTPS (educational, not for clinical use)"
    now = datetime.datetime.now()
    ds.InstanceCreationDate, ds.InstanceCreationTime = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
    return ds


def _save(ds, path):
    ds.save_as(path, enforce_file_format=True) if "enforce_file_format" in ds.save_as.__code__.co_varnames else ds.save_as(path, write_like_original=False)


ENERGY_MV = {"6X": 6, "10X": 10, "15X": 15, "18X": 18}


def save_rtplan(path: str, plan, img):
    """RT Plan with jaws, MLC and MU per beam (control points as sequenced). Marked as educational."""
    from pydicom.dataset import Dataset
    from .beams import LEAF_EDGES
    ds = _base_ds(path, "1.2.840.10008.5.1.4.1.1.481.5", "RTPLAN", img, "PyTPS plan (educational)")
    ds.RTPlanLabel = plan.name[:16]; ds.RTPlanName = plan.name[:64]; ds.RTPlanGeometry = "PATIENT"
    ds.RTPlanDescription = "Educational plan from PyTPS. NOT FOR CLINICAL USE."
    ds.ApprovalStatus = "UNAPPROVED"
    pos = img.orientation if img.orientation in ("HFS", "FFS", "HFP", "FFP") else "HFS"
    ps = Dataset(); ps.PatientPosition = pos; ps.PatientSetupNumber = 1; ds.PatientSetupSequence = [ps]
    dr = Dataset(); dr.DoseReferenceNumber = 1; dr.DoseReferenceStructureType = "SITE"; dr.DoseReferenceType = "TARGET"
    dr.TargetPrescriptionDose = f"{plan.rx.dose:.3f}"; dr.DoseReferenceDescription = plan.rx.target[:64]
    ds.DoseReferenceSequence = [dr]
    fg = Dataset(); fg.FractionGroupNumber = 1; fg.NumberOfFractionsPlanned = int(plan.rx.fractions)
    fg.NumberOfBeams = len(plan.beams); fg.NumberOfBrachyApplicationSetups = 0; fg.ReferencedBeamSequence = []
    ds.BeamSequence = []
    for n, b in enumerate(plan.beams, start=1):
        rb = Dataset(); rb.ReferencedBeamNumber = n; rb.BeamMeterset = f"{b.mu:.3f}"; fg.ReferencedBeamSequence.append(rb)
        bs = Dataset(); bs.BeamNumber = n; bs.BeamName = b.name[:16]; bs.BeamType = "DYNAMIC" if (b.kind == "ARC" or len(b.cps) > 1) else "STATIC"
        bs.RadiationType = "PHOTON"; bs.TreatmentMachineName = "PyTPS-EDU"; bs.PrimaryDosimeterUnit = "MU"; bs.SourceAxisDistance = "1000"
        bs.TreatmentDeliveryType = "TREATMENT"
        devs = []
        for t, num in (("ASYMX", 1), ("ASYMY", 1), ("MLCX", len(LEAF_EDGES) - 1)):
            d = Dataset(); d.RTBeamLimitingDeviceType = t; d.NumberOfLeafJawPairs = num
            if t == "MLCX":
                d.LeafPositionBoundaries = [f"{v:.1f}" for v in LEAF_EDGES]
            devs.append(d)
        bs.BeamLimitingDeviceSequence = devs
        if b.wedge.angle:
            w = Dataset(); w.WedgeNumber = 1; w.WedgeType = "STANDARD"; w.WedgeAngle = f"{b.wedge.angle:g}"
            w.WedgeOrientation = {"+X": 90, "-X": 270, "+Y": 0, "-Y": 180}.get(b.wedge.direction, 0); w.WedgeID = b.wedge.direction
            bs.WedgeSequence = [w]; bs.NumberOfWedges = 1
        else:
            bs.NumberOfWedges = 0
        bs.NumberOfCompensators = 0; bs.NumberOfBoli = 0; bs.NumberOfBlocks = 0
        cps = b.control_points()
        # step-and-shoot: two control points per segment; arcs: one per control point plus the end
        seq, cum = [], 0.0
        pairs = [(c, c) for c in cps] if b.kind != "ARC" else [(c,) for c in cps]
        total_w = sum(c.weight for c in cps) or 1.0
        for k, grp in enumerate(pairs):
            for r, c in enumerate(grp):
                cpd = Dataset(); cpd.ControlPointIndex = len(seq)
                if len(seq) == 0:
                    cpd.NominalBeamEnergy = ENERGY_MV.get(b.energy, 6); cpd.GantryRotationDirection = ("CW" if b.arc_dir == "CW" else "CC") if b.kind == "ARC" else "NONE"
                    cpd.BeamLimitingDeviceAngle = f"{c.collimator:.1f}"; cpd.BeamLimitingDeviceRotationDirection = "NONE"
                    cpd.PatientSupportAngle = f"{c.couch:.1f}"; cpd.PatientSupportRotationDirection = "NONE"
                    cpd.IsocenterPosition = [f"{v:.2f}" for v in b.iso]
                cpd.GantryAngle = f"{c.gantry:.2f}"
                pos = []
                for t, vals in (("ASYMX", [c.x1, c.x2]), ("ASYMY", [c.y1, c.y2])):
                    dp = Dataset(); dp.RTBeamLimitingDeviceType = t; dp.LeafJawPositions = [f"{v:.1f}" for v in vals]; pos.append(dp)
                left = c.left if c.left is not None else np.clip(np.full(len(LEAF_EDGES) - 1, c.x1), -200, 200)
                right = c.right if c.right is not None else np.clip(np.full(len(LEAF_EDGES) - 1, c.x2), -200, 200)
                dp = Dataset(); dp.RTBeamLimitingDeviceType = "MLCX"; dp.LeafJawPositions = [f"{v:.1f}" for v in list(left) + list(right)]; pos.append(dp)
                cpd.BeamLimitingDevicePositionSequence = pos
                if b.kind != "ARC" and r == 1:
                    cum += c.weight / total_w
                cpd.CumulativeMetersetWeight = f"{min(cum, 1.0):.6f}"
                if b.kind == "ARC":
                    cum += c.weight / total_w
                seq.append(cpd)
        if b.kind == "ARC":
            end = Dataset(); end.ControlPointIndex = len(seq); end.GantryAngle = f"{b.arc_stop:.2f}"; end.CumulativeMetersetWeight = "1.000000"
            seq.append(end)
        bs.NumberOfControlPoints = len(seq); bs.ControlPointSequence = seq; bs.FinalCumulativeMetersetWeight = "1.0"
        ds.BeamSequence.append(bs)
    ds.FractionGroupSequence = [fg]
    _save(ds, path)


def load_rtplan(path: str, energies=("6X", "10X")):
    """Beams (geometry, jaws, MLC control points, MU) from an RT Plan. Returns (beams, (dose, fractions) or None)."""
    pydicom = _pydicom()
    from .beams import Beam, ControlPoint, Wedge
    ds = pydicom.dcmread(path, force=True)
    mu = {}
    nfx = None
    for fg in getattr(ds, "FractionGroupSequence", []):
        nfx = int(getattr(fg, "NumberOfFractionsPlanned", 1) or 1)
        for rb in getattr(fg, "ReferencedBeamSequence", []):
            mu[int(rb.ReferencedBeamNumber)] = float(getattr(rb, "BeamMeterset", 0) or 0)
    rx = None
    for dr in getattr(ds, "DoseReferenceSequence", []):
        if hasattr(dr, "TargetPrescriptionDose"):
            rx = (float(dr.TargetPrescriptionDose), nfx or 1)
    beams = []
    for bs in getattr(ds, "BeamSequence", []):
        if str(getattr(bs, "TreatmentDeliveryType", "TREATMENT")) != "TREATMENT":
            continue
        cps = list(bs.ControlPointSequence)
        c0 = cps[0]
        e = f"{int(round(float(getattr(c0, 'NominalBeamEnergy', 6))))}X"
        if e not in energies:
            e = min(energies, key=lambda x: abs(int(x[:-1]) - int(e[:-1])))
        iso = np.array([float(v) for v in c0.IsocenterPosition])
        b = Beam(str(getattr(bs, "BeamName", f"B{bs.BeamNumber}"))[:16], iso, energy=e,
                 gantry=float(c0.GantryAngle), collimator=float(getattr(c0, "BeamLimitingDeviceAngle", 0)),
                 couch=float(getattr(c0, "PatientSupportAngle", 0)))
        rot = str(getattr(c0, "GantryRotationDirection", "NONE"))
        if rot in ("CW", "CC"):
            b.kind = "ARC"; b.arc_dir = "CW" if rot == "CW" else "CCW"; b.arc_stop = float(cps[-1].GantryAngle)
        bounds = None
        for d in getattr(bs, "BeamLimitingDeviceSequence", []):
            if "MLC" in str(d.RTBeamLimitingDeviceType):
                bounds = np.array([float(v) for v in getattr(d, "LeafPositionBoundaries", [])])
        if len(getattr(bs, "WedgeSequence", [])):
            w = bs.WedgeSequence[0]
            b.wedge = Wedge(float(w.WedgeAngle), {90: "+X", 270: "-X", 0: "+Y", 180: "-Y"}.get(int(float(getattr(w, "WedgeOrientation", 0))), "+X"))
        state = {"g": b.gantry, "jx": [-50.0, 50.0], "jy": [-50.0, 50.0], "mlc": None, "w": 0.0}
        out = []
        from .beams import LEAF_CENTRES
        for c in cps:
            if hasattr(c, "GantryAngle"):
                state["g"] = float(c.GantryAngle)
            for dp in getattr(c, "BeamLimitingDevicePositionSequence", []):
                t, v = str(dp.RTBeamLimitingDeviceType), [float(x) for x in dp.LeafJawPositions]
                if t in ("ASYMX", "X"):
                    state["jx"] = v[:2]
                elif t in ("ASYMY", "Y"):
                    state["jy"] = v[:2]
                elif "MLC" in t:
                    n = len(v) // 2; L, R = np.array(v[:n]), np.array(v[n:])
                    if bounds is not None and len(bounds) == n + 1:
                        cen = 0.5 * (bounds[1:] + bounds[:-1])
                        L, R = np.interp(LEAF_CENTRES, cen, L, left=0, right=0), np.interp(LEAF_CENTRES, cen, R, left=0, right=0)
                    state["mlc"] = (L, R)
            wcum = float(getattr(c, "CumulativeMetersetWeight", state["w"]))
            dw = wcum - state["w"]; state["w"] = wcum
            out.append((state["g"], list(state["jx"]), list(state["jy"]), state["mlc"], dw))
        b.x1, b.x2 = out[0][1]; b.y1, b.y2 = out[0][2]
        cpl = []
        if b.kind == "ARC":
            for k in range(1, len(out)):
                g0, g1 = out[k - 1][0], out[k][0]
                gm = (g0 + ((g1 - g0 + 180) % 360 - 180) / 2) % 360
                m = out[k - 1][3]
                cpl.append(ControlPoint(gm, b.collimator, b.couch, *out[k - 1][1], *out[k - 1][2], None if m is None else m[0], None if m is None else m[1], max(out[k][4], 0)))
        else:
            for k in range(1, len(out)):
                if out[k][4] > 0:
                    m = out[k][3]
                    cpl.append(ControlPoint(b.gantry, b.collimator, b.couch, *out[k][1], *out[k][2], None if m is None else m[0], None if m is None else m[1], out[k][4]))
        if cpl:
            b.cps = cpl
            if cpl[0].left is not None:
                b.mlc_mode = "manual"; b.left, b.right = cpl[0].left.copy(), cpl[0].right.copy()
        b.mu = mu.get(int(bs.BeamNumber), 0.0)
        beams.append(b)
    return beams, rx


def save_rtdose(path: str, vol, spacing, origin, img):
    """RT Dose (Gy) on an axis-aligned grid."""
    ds = _base_ds(path, "1.2.840.10008.5.1.4.1.1.481.2", "RTDOSE", img, "PyTPS dose (educational)")
    vol = np.asarray(vol, np.float32)
    scale = float(vol.max()) / 65000 if vol.max() > 0 else 1.0
    data = np.round(vol / scale).astype(np.uint32)
    ds.DoseUnits = "GY"; ds.DoseType = "PHYSICAL"; ds.DoseSummationType = "PLAN"; ds.DoseGridScaling = f"{scale:.10g}"
    ds.ImagePositionPatient = [f"{v:.3f}" for v in origin]; ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [f"{spacing:.4f}", f"{spacing:.4f}"]; ds.SliceThickness = f"{spacing:.4f}"
    ds.GridFrameOffsetVector = [f"{k * spacing:.3f}" for k in range(vol.shape[0])]
    ds.NumberOfFrames = vol.shape[0]; ds.FrameIncrementPointer = (0x3004, 0x000C)
    ds.Rows, ds.Columns = vol.shape[1], vol.shape[2]
    ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = "MONOCHROME2"; ds.BitsAllocated = 32; ds.BitsStored = 32; ds.HighBit = 31
    ds.PixelRepresentation = 0
    ds.PixelData = data.tobytes()
    _save(ds, path)
