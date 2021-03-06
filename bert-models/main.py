from data_preprocessing import merge_data
from helpers import train, evaluate
import numpy as np
import random
import torch
from torchtext.legacy import data
from torch.nn import CrossEntropyLoss
import torch.optim as optim
from transformers import BertTokenizer, BertModel
from models import BERTClassification, SimpleBERT

SEED = 1234

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.backends.cudnn.deterministic = True

bert = BertModel.from_pretrained("bert-base-uncased")

# Dataset reading paths.
PathToTrainLabels = "../data/ClarificationTask_TrainLabels_Sep23.tsv"
PathToTrainData = "../data/ClarificationTask_TrainData_Sep23.tsv"
PathToDevLabels = "../data/ClarificationTask_DevLabels_Dec12.tsv"
PathToDevData = "../data/ClarificationTask_DevData_Oct22a.tsv"

# Model parameters
tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
PAD_INDEX = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)
UNK_INDEX = tokenizer.convert_tokens_to_ids(tokenizer.unk_token)
MAX_SEQ_LEN = 100
HIDDEN_DIM = 256
OUTPUT_DIM = 3
N_LAYERS = 2
BIDIRECTIONAL = True
DROPOUT = 0.25
N_EPOCHS = 10
USE_CONTEXT = True
FILLER_MARKERS = None
ADD_FILLER_MARKERS_TO_SPECIAL_TOKENS = False
MODEL_NAME = "baseline-model.pt"


# set sequential = False, those fields are not texts.
ids = data.RawField()
label = data.Field(
    sequential=False, use_vocab=False, batch_first=True, dtype=torch.float
)
# label = data.LabelField(dtype=torch.float)
# set use_vocab=False to use own decoder
text = data.Field(
    use_vocab=False,
    tokenize=tokenizer.encode,
    lower=False,
    include_lengths=False,
    batch_first=True,
    fix_length=MAX_SEQ_LEN,
    pad_token=PAD_INDEX,
    unk_token=UNK_INDEX,
)

text.build_vocab()

fields = {"ids": ("ids", ids), "text": ("text", text), "label": ("label", label)}


def read_data(use_context):
    """
    :param: use_context: boolean indicating whether the text should contain the sentence+filler (use_context=False)
    or sentence+filler in context (use_context=True)
    :return:
    * train and development set in BucketIterator format.
    """
    if use_context:
        train_df = merge_data(
            path_to_instances=PathToTrainData,
            path_to_labels=PathToTrainLabels,
            filler_markers=FILLER_MARKERS,
            use_context=use_context,
        )
        development_df = merge_data(
            path_to_instances=PathToDevData,
            path_to_labels=PathToDevLabels,
            filler_markers=FILLER_MARKERS,
            use_context=use_context,
        )
        train_df.to_csv("./data/train.csv", index=False)
        development_df.to_csv("./data/dev.csv", index=False)

    else:
        train_df = merge_data(
            path_to_instances=PathToTrainData,
            path_to_labels=PathToTrainLabels,
            filler_markers=FILLER_MARKERS,
            use_context=use_context,
        )
        development_df = merge_data(
            path_to_instances=PathToDevData,
            path_to_labels=PathToDevLabels,
            filler_markers=FILLER_MARKERS,
            use_context=use_context,
        )
        train_df.to_csv("./data/train.csv", index=False)
        development_df.to_csv("./data/dev.csv", index=False)

    train_data, valid_data, test_data = data.TabularDataset.splits(
        path="data",
        train="train.csv",
        validation="dev.csv",
        test="dev.csv",
        format="csv",
        fields=fields,
        skip_header=False,
    )
    # label.build_vocab(train_data)
    print("Train instances:", len(train_data))
    print("Dev instances:", len(valid_data))
    train_iter = data.BucketIterator(
        train_data,
        batch_size=16,
        sort_key=lambda x: len(x.text),
        train=True,
        sort=True,
        sort_within_batch=True,
    )
    valid_iter = data.BucketIterator(
        valid_data,
        batch_size=16,
        sort_key=lambda x: len(x.text),
        train=True,
        sort=True,
        sort_within_batch=True,
    )

    test_iter = data.Iterator(
        test_data, batch_size=16, train=False, shuffle=False, sort=False
    )
    return train_iter, valid_iter, test_iter


def main():
    # read data and return buckets
    # at the moment, do not use the test data.
    train_iter, valid_iter, _ = read_data(use_context=USE_CONTEXT)

    # check the parameters
    # initialize the model.
    # model = BERTClassification(bert,
    #                        HIDDEN_DIM,
    #                        OUTPUT_DIM,
    #                        N_LAYERS,
    #                        BIDIRECTIONAL,
    #                        DROPOUT)
    
    model = SimpleBERT(bert, OUTPUT_DIM)

    # add filler markers to tokenizer vocabulary if necessary
    if FILLER_MARKERS and ADD_FILLER_MARKERS_TO_SPECIAL_TOKENS:
        tokenizer.add_special_tokens({"additional_special_tokens": FILLER_MARKERS})
        bert.resize_token_embeddings(len(tokenizer))

    # check the parameters 
    print("training the following parameters .... ")
    for name, param in model.named_parameters():
        if param.requires_grad:
            print(name)

    optimizer = optim.Adam(model.parameters())

    criterion = CrossEntropyLoss()

    model = model.to(device)
    criterion = criterion.to(device)

    best_valid_loss = float("inf")
    for epoch in range(N_EPOCHS):
        train_loss, train_acc = train(model, train_iter, optimizer, criterion, device)
        valid_loss, valid_acc = evaluate(model, valid_iter, criterion, device, epoch, MODEL_NAME)

        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            torch.save(model.state_dict(), MODEL_NAME)

        print("Epoch: {0}".format(epoch))
        print(f"\tTrain Loss: {train_loss:.3f} | Train Acc: {train_acc*100:.2f}%")
        print(f"\t Val. Loss: {valid_loss:.3f} |  Val. Acc: {valid_acc*100:.2f}%")


main()
