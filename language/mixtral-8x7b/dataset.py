import random
import os
import time
import numpy as np
import torch
from datasets import load_dataset, load_from_disk
from transformers import AutoModelForCausalLM, AutoTokenizer
from torch.nn.functional import pad
from torch.utils.data import DataLoader
from typing import Optional, Dict, Sequence
import io

# import utils
import copy
import pickle

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Llama-70B-Dataset")


class Dataset:
    def __init__(
        self,
        model_name=None,
        total_sample_count=15000,
        perf_count_override=None,
        dataset_path=None,
        device="cpu",
    ):
        self.model_name = model_name or "mistralai/Mixtral-8x7B-v0.1"
        self.dataset_path = dataset_path
        self.max_length = 1024
        self.device = device

        # self.total_sample_count = total_sample_count

        self.load_tokenizer()
        self.load_processed_dataset()

        self.total_sample_count = min(len(self.input_ids), total_sample_count)
        self.perf_count = perf_count_override or self.total_sample_count

    def load_tokenizer(self):
        """Returns tokenizer"""
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            model_max_length=1024,
            padding_side="left",
            use_fast=False,
        )

        self.tokenizer.pad_token = self.tokenizer.eos_token

    def load_processed_dataset(self):
        if not os.path.isfile(self.dataset_path):
            log.warn(
                "Processed pickle file {} not found. Please check that the path is correct".format(
                    self.dataset_path
                )
            )

        print("Loading dataset...")
        import pandas as pd

        processed_data = pd.read_pickle(self.dataset_path)

        input_tokens = processed_data["tok_input"]
        self.input_texts = processed_data["input"].to_list()

        self.input_ids = []
        self.input_lens = []
        self.attention_masks = []
        self.dataset_names = []

        for ids in input_tokens:
            input_ids = torch.tensor(ids, dtype=torch.int32).view(
                1, -1).to(self.device)
            attn_mask = torch.ones_like(input_ids)
            self.input_ids.append(input_ids)
            self.attention_masks.append(attn_mask)
            self.input_lens.append(input_ids.shape[-1])

        for dataset in processed_data["dataset"]:
            self.dataset_names.append(dataset)
        print("Finished loading dataset.")

    def remove_trailing_twos(self, lst, eos=2):
        count = 0
        for num in reversed(lst):
            if num == eos or num == 0:
                count += 1
            else:
                break
        return lst[:-count] if count > 0 else lst

    def mbxp_stop(self, lst, stop_tokens=[13, 13940, 28832, 13]):
        for i in range(len(lst) - len(stop_tokens) + 1):
            if (lst[i:i + len(stop_tokens)] == stop_tokens).all():
                return lst[:i + len(stop_tokens)]
        return lst

    def postProcess(
        self,
        out_tokens,
        length=None,
        query_id_list=None,
        sample_index_list=None,
        dataset_list=None,
    ):
        """Postprocesses output prediction"""

        # TODO: Create response object in postProcess(?)
        """
        preds = []
        for i in range(out_tokens.shape[0]):
            #pred = out_tokens[i].reshape(-1).cpu().numpy() # Slice up to original input length as below?

            input_len = input_seq_lens[i] if input_seq_lens else 0
            pred = out_tokens[i, input_len:].reshape(-1).cpu().numpy()
            preds.append(pred)
        """
        # Everything is padded to max_len (1024), so prune the input and parse
        # to numpy
        output_seq = out_tokens[:, length:].cpu().numpy()
        aux_seq = []
        assert len(query_id_list) == output_seq.shape[0]
        for i in range(len(output_seq)):
            aux = output_seq[i]
            aux = self.remove_trailing_twos(aux)
            if (dataset_list[i] == "MBXP"):
                aux = self.mbxp_stop(aux)
            aux_seq.append(aux)
        output_seq = np.stack(aux_seq)

        # Save outputs
        if not os.path.exists("run_outputs"):
            os.makedirs("run_outputs")
        fname = "q" + "_".join([str(i) for i in query_id_list])
        fname = f"run_outputs/{fname}.pkl"
        with open(fname, mode="wb") as f:
            d = {"query_ids": query_id_list, "outputs": output_seq}
            print(f"Saving outputs to {fname}")
            pickle.dump(d, f)

        return output_seq

    def LoadSamplesToRam(self, sample_list):
        pass

    def UnloadSamplesFromRam(self, sample_list):
        pass

    def __del__(self):
        pass
